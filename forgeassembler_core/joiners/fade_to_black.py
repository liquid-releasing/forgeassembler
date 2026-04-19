# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""FadeToBlack: fade out the previous segment, hold a solid colour
frame, fade in the next. Default colour is black, but any hex colour
works (dark grey, deep blue, etc.) — the joiner type name is kept for
backward compat but the behaviour is `fade_to_color`.

`duration_s` is the total solid-colour bridge time. The adjacent
segments get small fades (capped at 0.5s per side) at the boundary.
"""

from __future__ import annotations

from typing import Any

from .base import Joiner

DEFAULT_FADE_COLOR = "#000000"


class FadeToBlack(Joiner):
    joiner_type = "fade_to_black"
    display_name = "Fade to colour"
    description = (
        "Previous segment fades into a solid colour bridge (default "
        "black), which holds for `duration_s` seconds, then the next "
        "segment fades in. Audio is silent during the bridge."
    )

    DEFAULT_DURATION_S: float = 1.0

    def duration_ms(self) -> int:
        return int(round(self._duration_s() * 1000))

    def _duration_s(self) -> float:
        d = self.params.get("duration_s", self.DEFAULT_DURATION_S)
        try:
            d = float(d)
        except (TypeError, ValueError):
            d = self.DEFAULT_DURATION_S
        return max(0.0, d)

    def color(self) -> str:
        """Return the bridge colour as a hex string (e.g. '#1a1a1a').

        Missing or invalid values fall back to black.
        """
        raw = self.params.get("color", DEFAULT_FADE_COLOR)
        if not isinstance(raw, str) or not raw:
            return DEFAULT_FADE_COLOR
        raw = raw.strip()
        if not raw.startswith("#"):
            raw = "#" + raw
        # Only accept 7-char hex like '#rrggbb'
        if len(raw) != 7 or not all(c in "0123456789abcdefABCDEF" for c in raw[1:]):
            return DEFAULT_FADE_COLOR
        return raw.lower()

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self._duration_s() <= 0:
            errors.append("FadeToBlack duration_s must be > 0.")
        return errors

    @classmethod
    def params_schema(cls) -> dict[str, Any]:
        return {
            "duration_s": {
                "type": "float",
                "default": cls.DEFAULT_DURATION_S,
                "min": 0.1,
                "max": 10.0,
                "label": "Duration (seconds)",
                "help": "Length of the solid-colour bridge.",
            },
            "color": {
                "type": "color",
                "default": DEFAULT_FADE_COLOR,
                "label": "Bridge colour",
                "help": "Hex colour of the bridge (e.g. '#000000' black, "
                        "'#1a1a1a' dark grey).",
            },
        }
