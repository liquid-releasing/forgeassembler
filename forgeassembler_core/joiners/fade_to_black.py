# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""FadeToBlack: fade out the previous segment, hold black, fade in the next.

In v1 we model the fade as a crossfade-through-black using ffmpeg's
`xfade` filter with the `fadeblack` transition. `duration_s` is the
total duration of the xfade (half fade-out + half fade-in) so the
joiner occupies `duration_s` of output time.

A future param `black_hold_s` (Phase 2) would extend the held-black
portion in the middle.
"""

from __future__ import annotations

from typing import Any

from .base import Joiner


class FadeToBlack(Joiner):
    joiner_type = "fade_to_black"
    display_name = "Fade to black"
    description = (
        "Previous segment fades out while black fades in, then black fades out "
        "while the next segment fades in. Audio is cross-faded in lockstep."
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
                "help": "Total fade duration including fade-out, hold, and fade-in.",
            },
        }
