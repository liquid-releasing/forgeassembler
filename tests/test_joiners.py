# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Unit tests for joiner registry + individual joiners."""

from __future__ import annotations

import pytest

from forgeassembler_core.joiners import REGISTRY, all_specs, instantiate
from forgeassembler_core.joiners.fade_to_black import FadeToBlack
from forgeassembler_core.joiners.none_joiner import NoneJoiner


def test_registry_contains_core_types():
    assert "none" in REGISTRY
    assert "fade_to_black" in REGISTRY


def test_instantiate_unknown_raises():
    with pytest.raises(ValueError):
        instantiate("does_not_exist")


def test_none_joiner_has_zero_duration():
    j = instantiate("none")
    assert j.duration_ms() == 0


def test_fade_to_black_duration_default():
    j = instantiate("fade_to_black")
    # Default hold is 5s (new decoupled fade/hold model — fade_s=1.0,
    # duration_s=5.0). duration_ms is the HOLD length (added to output).
    assert j.duration_ms() == 5000


def test_fade_to_black_duration_respects_param():
    j = instantiate("fade_to_black", {"duration_s": 2.5})
    assert j.duration_ms() == 2500


def test_fade_to_black_validate_catches_both_zero():
    """duration_s=0 is fine alone (pure crossfade through black), but
    the joiner can't be a complete no-op — require fade_s or hold."""
    j = FadeToBlack({"duration_s": 0, "fade_s": 0})
    errors = j.validate()
    assert any("no-op" in e for e in errors)


def test_fade_to_black_validate_allows_hold_zero_with_fade():
    """Hold 0 + fade 1 is a valid pure crossfade-through-black."""
    j = FadeToBlack({"duration_s": 0, "fade_s": 1.0})
    assert j.validate() == []


def test_fade_to_black_validate_rejects_negative():
    j = FadeToBlack({"duration_s": -1, "fade_s": 1.0})
    assert any("duration_s" in e for e in j.validate())


def test_fade_to_black_ignores_bad_type():
    j = FadeToBlack({"duration_s": "not a number"})
    # Falls back to class default — now 5.0s.
    assert j.duration_ms() == 5000


def test_fade_to_black_fade_s_default():
    """Per-side fade defaults to 1.0s when not specified."""
    j = FadeToBlack({})
    assert j.fade_s() == 1.0


def test_fade_to_black_fade_s_respects_param():
    j = FadeToBlack({"fade_s": 2.5})
    assert j.fade_s() == 2.5


def test_fade_to_black_fade_s_ignores_bad_type():
    j = FadeToBlack({"fade_s": "not a number"})
    assert j.fade_s() == 1.0


def test_all_specs_includes_param_schemas():
    specs = all_specs()
    types = {s.joiner_type for s in specs}
    assert "none" in types
    assert "fade_to_black" in types
    fade = next(s for s in specs if s.joiner_type == "fade_to_black")
    assert "duration_s" in fade.params_schema


def test_none_joiner_no_params():
    j = NoneJoiner()
    assert j.validate() == []
    assert j.duration_ms() == 0
