# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Joiner abstract base class.

A Joiner represents the transition between two adjacent segments in a
project. It reports its own occupying duration (which may be zero for a
hard cut, or several seconds for a fade), and ultimately emits ffmpeg
filter_complex fragments at concat time.

V1 only needs duration + metadata; the ffmpeg fragment methods are
stubs until the video concat module is built out.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar


@dataclass
class JoinerSpec:
    """Metadata for the joiner library UI — what params it accepts, etc."""
    joiner_type: str
    display_name: str
    description: str
    params_schema: dict[str, Any] = field(default_factory=dict)


class Joiner(ABC):
    """Abstract joiner. Subclasses register in `joiners/__init__.py`."""

    joiner_type: ClassVar[str] = ""
    display_name: ClassVar[str] = ""
    description: ClassVar[str] = ""

    def __init__(self, params: dict | None = None) -> None:
        self.params: dict = dict(params or {})

    # ── Required interface ────────────────────────────────────────
    @abstractmethod
    def duration_ms(self) -> int:
        """How many ms this joiner occupies in the output timeline."""

    # ── Default interface (subclasses may override) ───────────────
    def validate(self) -> list[str]:
        """Return a list of human-readable error messages, empty if valid."""
        return []

    # ── Metadata for the registry ─────────────────────────────────
    @classmethod
    def spec(cls) -> JoinerSpec:
        return JoinerSpec(
            joiner_type=cls.joiner_type,
            display_name=cls.display_name,
            description=cls.description,
            params_schema=cls.params_schema(),
        )

    @classmethod
    def params_schema(cls) -> dict[str, Any]:
        """Simple schema the UI can render as form fields.

        Format:
        {
          "param_name": {"type": "float|int|str|bool",
                         "default": ..., "min": ..., "max": ...,
                         "label": "...", "help": "..."}
        }
        """
        return {}

    @classmethod
    def from_params(cls, params: dict) -> "Joiner":
        return cls(params=params)
