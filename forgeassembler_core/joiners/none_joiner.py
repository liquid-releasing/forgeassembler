# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""NoneJoiner: a straight cut with zero duration."""

from __future__ import annotations

from .base import Joiner


class NoneJoiner(Joiner):
    joiner_type = "none"
    display_name = "None (straight cut)"
    description = "No transition — the next segment begins the instant the previous one ends."

    def duration_ms(self) -> int:
        return 0
