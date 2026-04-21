# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Unit tests for ffmpeg filter-chain string builders."""

from __future__ import annotations

import pytest

from forgeassembler_core.filters import (
    bug_overlay_filter,
    bug_prepare_filter,
    concat_filter,
    corner_position_expr,
    fade_to_black_audio_acrossfade,
    fade_to_black_xfade,
    image_overlay_filter,
    loudnorm_filter,
    normalize_segment_filter,
)


# ── normalize_segment_filter ──────────────────────────────────────────
def test_normalize_segment_basic():
    s = normalize_segment_filter("v_in", "v_out", 1920, 1080)
    assert s.startswith("[v_in]")
    assert s.endswith("[v_out]")
    assert "scale=1920:1080:force_original_aspect_ratio=decrease" in s
    assert "pad=1920:1080:(ow-iw)/2:(oh-ih)/2" in s
    assert "setsar=1" in s
    assert "colortemperature" not in s


def test_normalize_segment_with_color_temp():
    s = normalize_segment_filter("v0", "v0_warm", 2560, 1080, color_temperature_k=6200)
    assert s.endswith("[v0_warm]")
    assert "colortemperature=temperature=6200" in s


def test_normalize_segment_different_resolutions():
    s_1080p = normalize_segment_filter("v", "o", 1920, 1080)
    s_uw = normalize_segment_filter("v", "o", 3440, 1440)
    s_portrait = normalize_segment_filter("v", "o", 1080, 1920)
    assert "1920:1080" in s_1080p
    assert "3440:1440" in s_uw
    assert "1080:1920" in s_portrait


# ── corner_position_expr ──────────────────────────────────────────────
@pytest.mark.parametrize("corner,expected_x,expected_y", [
    ("tl", "24",        "24"),
    ("tr", "W-w-24",    "24"),
    ("bl", "24",        "H-h-24"),
    ("br", "W-w-24",    "H-h-24"),
])
def test_corner_position_expr_all_corners(corner, expected_x, expected_y):
    x, y = corner_position_expr(corner, 24)
    assert x == expected_x
    assert y == expected_y


def test_corner_position_zero_margin():
    x, y = corner_position_expr("br", 0)
    assert x == "W-w-0"
    assert y == "H-h-0"


def test_corner_position_rejects_unknown():
    with pytest.raises(ValueError):
        corner_position_expr("middle", 10)  # type: ignore[arg-type]


# ── bug_prepare_filter ────────────────────────────────────────────────
def test_bug_prepare_basic():
    s = bug_prepare_filter("bug_in", "bug_out", 0.85)
    assert s == "[bug_in]format=rgba,colorchannelmixer=aa=0.85[bug_out]"


def test_bug_prepare_clamps_opacity():
    s_low = bug_prepare_filter("b", "o", -0.5)
    s_high = bug_prepare_filter("b", "o", 1.5)
    assert "aa=0" in s_low
    assert "aa=1" in s_high


# ── bug_overlay_filter ────────────────────────────────────────────────
def test_bug_overlay_basic():
    s = bug_overlay_filter("v", "bug_rgba", "v_bugged", "br", 24)
    assert s.startswith("[v][bug_rgba]")
    assert s.endswith("[v_bugged]")
    assert "overlay=x=W-w-24:y=H-h-24" in s
    assert ":format=auto" in s


def test_bug_overlay_top_left():
    s = bug_overlay_filter("v", "bug", "out", "tl", 12)
    assert "x=12:y=12" in s


# ── fade_to_black_xfade ───────────────────────────────────────────────
def test_fade_to_black_xfade_basic():
    s = fade_to_black_xfade("a", "b", "out", 2.0, 5.0)
    assert s == "[a][b]xfade=transition=fadeblack:duration=2:offset=5[out]"


def test_fade_to_black_xfade_fractional_durations():
    s = fade_to_black_xfade("a", "b", "out", 1.5, 10.25)
    assert "duration=1.5" in s
    assert "offset=10.25" in s


# ── fade_to_black_audio_acrossfade ────────────────────────────────────
def test_audio_acrossfade_basic():
    s = fade_to_black_audio_acrossfade("a0", "a1", "aout", 2.0)
    assert s == "[a0][a1]acrossfade=d=2:c1=tri:c2=tri[aout]"


# ── concat_filter ─────────────────────────────────────────────────────
def test_concat_filter_two_segments():
    s = concat_filter([("v0", "a0"), ("v1", "a1")], "vout", "aout")
    assert s == "[v0][a0][v1][a1]concat=n=2:v=1:a=1[vout][aout]"


def test_concat_filter_many_segments():
    pairs = [(f"v{i}", f"a{i}") for i in range(5)]
    s = concat_filter(pairs, "V", "A")
    assert "concat=n=5:v=1:a=1" in s
    for i in range(5):
        assert f"[v{i}][a{i}]" in s
    assert s.endswith("[V][A]")


def test_concat_filter_rejects_empty():
    with pytest.raises(ValueError):
        concat_filter([], "v", "a")


# ── loudnorm_filter ───────────────────────────────────────────────────
def test_loudnorm_defaults_match_youtube():
    s = loudnorm_filter("in", "out")
    assert s == "[in]loudnorm=I=-16:TP=-1.5:LRA=11[out]"


def test_loudnorm_custom_targets():
    s = loudnorm_filter("in", "out", integrated_lufs=-14.0, true_peak_dbfs=-1.0)
    assert "I=-14" in s
    assert "TP=-1" in s


# ── image_overlay_filter ──────────────────────────────────────────────
def test_image_overlay_center_no_window():
    s = image_overlay_filter("v", "img", "out")
    assert s.startswith("[v][img]")
    assert s.endswith("[out]")
    assert "overlay=x=(W-w)/2:y=(H-h)/2" in s
    assert "enable=" not in s


def test_image_overlay_with_window():
    s = image_overlay_filter("v", "img", "out", start_s=1.0, end_s=4.5)
    assert "enable='between(t,1,4.5)'" in s


def test_image_overlay_start_only():
    s = image_overlay_filter("v", "img", "out", start_s=2.5)
    assert "enable='gte(t,2.5)'" in s


def test_image_overlay_partial_opacity_adds_prefix():
    s = image_overlay_filter("v", "img", "out", opacity=0.5)
    assert "[img]format=rgba,colorchannelmixer=aa=0.5[img_prep]" in s
    assert "[v][img_prep]" in s


def test_image_overlay_rejects_unknown_position():
    with pytest.raises(ValueError):
        image_overlay_filter("v", "img", "out", position="diagonal")


@pytest.mark.parametrize("position,expected", [
    ("center",        "x=(W-w)/2:y=(H-h)/2"),
    ("top-left",      "x=W*0.05:y=H*0.05"),
    ("top-right",     "x=W-w-W*0.05:y=H*0.05"),
    ("bottom-left",   "x=W*0.05:y=H-h-H*0.05"),
    ("bottom-right",  "x=W-w-W*0.05:y=H-h-H*0.05"),
    ("top-center",    "x=(W-w)/2:y=H*0.05"),
    ("bottom-center", "x=(W-w)/2:y=H-h-H*0.05"),
])
def test_image_overlay_positions(position, expected):
    s = image_overlay_filter("v", "img", "out", position=position)
    assert expected in s
