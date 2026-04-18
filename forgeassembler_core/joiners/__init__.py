# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Joiner registry. Register new joiner types by importing and adding to
REGISTRY below.
"""

from __future__ import annotations

from .base import Joiner, JoinerSpec
from .fade_to_black import FadeToBlack
from .none_joiner import NoneJoiner

REGISTRY: dict[str, type[Joiner]] = {
    NoneJoiner.joiner_type: NoneJoiner,
    FadeToBlack.joiner_type: FadeToBlack,
}


def instantiate(joiner_type: str, params: dict | None = None) -> Joiner:
    if joiner_type not in REGISTRY:
        raise ValueError(
            f"Unknown joiner type: {joiner_type!r}. "
            f"Available: {sorted(REGISTRY.keys())}"
        )
    cls = REGISTRY[joiner_type]
    return cls.from_params(params or {})


def all_specs() -> list[JoinerSpec]:
    return [cls.spec() for cls in REGISTRY.values()]


__all__ = ["Joiner", "JoinerSpec", "REGISTRY", "instantiate", "all_specs"]
