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
    assert any("title" in e for e in errors)
    assert _title().validate() == []


def test_a_subtitle_alone_is_enough_to_be_a_card():
    # "INTERMISSION" in the eyebrow slot is a legitimate card; only a
    # card with nothing at all in it is a fade wearing a costume.
    assert _instantiate(
        "title_card", {"duration_s": 3.0, "eyebrow": "intermission"},
    ).validate() == []


def test_title_card_needs_a_frame_to_draw_on():
    errors = _title(duration_s=0).validate()
    assert any("duration_s" in e for e in errors)


def test_title_card_errors_name_the_thing_the_user_picked():
    # The parent's messages say "FadeToBlack", which is not what the
    # user chose in the UI.
    for e in _title(duration_s=-1).validate():
        assert "FadeToBlack" not in e


def test_a_cards_words_survive_the_old_param_name():
    # `text` was the only field the first title card had. A project
    # saved by that build has to keep saying the same thing.
    assert _instantiate("title_card", {"text": "Part Two"}).text() == "Part Two"
    assert _instantiate(
        "title_card", {"text": "old", "title": "new"},
    ).text() == "new"


def test_a_card_ignores_a_layout_it_has_never_heard_of():
    # Forward compatibility: a project written by a later build must
    # still forge here, as the plainest card rather than not at all.
    spec = _title(layout="hologram", theme="chartreuse", glyph="unicorn").title_spec()
    assert spec.layout == "centered"
    assert spec.theme == "dark"
    assert spec.glyph == "none"


def test_the_bridge_colour_follows_the_theme():
    # The card is composited ONTO the bridge and the fades either side
    # land on it, so a bridge that disagreed with the theme would open
    # and close every title card with a flash of the wrong colour.
    assert _title().color() == "#0e1117"          # the dark theme
    assert _title(theme="light").color() == "#fafafa"
    assert _title(theme="void").color() == "#000000"


def test_an_explicit_colour_still_beats_the_theme():
    # Someone deliberately putting a dark card in a light project is
    # making a choice, not a mistake -- and every project saved before
    # themes existed carries an explicit colour.
    assert _title(theme="light", color="#123456").color() == "#123456"
    assert _title(color="not-a-colour").color() == "#000000"


def test_theme_colours_reach_the_renderer():
    spec = _title(theme="light").title_spec()
    assert spec.foreground_color() == "#0e1117"
    assert _title(text_color="ffcc00").title_spec().foreground_color() == "#ffcc00"
    assert _title(accent_color="00ff00").title_spec().accent() == "#00ff00"


def test_title_card_is_registered():
    from forgeassembler_core.joiners import REGISTRY

    assert "title_card" in REGISTRY
