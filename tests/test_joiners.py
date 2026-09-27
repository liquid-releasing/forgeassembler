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


# ── Title card ────────────────────────────────────────────────────────
# A title card is a fade-to-colour bridge that carries words. It inherits
# FadeToBlack so its timing cannot drift from a plain fade's.

from forgeassembler_core.joiners import instantiate as _instantiate


def _title(**params):
    base = {"text": "Part Two", "duration_s": 3.0, "fade_s": 1.0}
    base.update(params)
    return _instantiate("title_card", base)


def test_title_card_duration_is_the_hold_only():
    # The fades live inside the neighbouring scenes and add no output
    # time, exactly as for a plain fade.
    assert _title().duration_ms() == 3000
    assert _title(fade_s=5.0).duration_ms() == 3000


def test_title_card_needs_words():
    errors = _instantiate("title_card", {"duration_s": 3.0}).validate()
    assert any("text" in e for e in errors)
    assert _title().validate() == []


def test_title_card_needs_a_frame_to_draw_on():
    errors = _title(duration_s=0).validate()
    assert any("duration_s" in e for e in errors)


def test_title_card_errors_name_the_thing_the_user_picked():
    # The parent's messages say "FadeToBlack", which is not what the
    # user chose in the UI.
    for e in _title(duration_s=-1).validate():
        assert "FadeToBlack" not in e


def test_title_card_rejects_a_font_size_ffmpeg_would_refuse():
    # An out-of-range drawtext option kills the whole filter graph at
    # setup rather than clamping, so a zero must never reach ffmpeg.
    assert _title(font_size=0).font_size() > 0
    assert _title(font_size=-10).font_size() > 0
    assert _title(font_size="nonsense").font_size() > 0


def test_title_card_defaults_to_white_on_black():
    t = _title()
    assert t.text_color() == "#ffffff"
    assert t.color() == "#000000"
    assert _title(text_color="ffcc00").text_color() == "#ffcc00"
    assert _title(text_color="not-a-colour").text_color() == "#ffffff"


def test_title_card_is_registered():
    from forgeassembler_core.joiners import REGISTRY

    assert "title_card" in REGISTRY
