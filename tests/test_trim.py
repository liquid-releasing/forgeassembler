# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Trim windows + split-at-time (v0.0.3 trim & split feature)."""

from __future__ import annotations

from pathlib import Path

import pytest

from forgeassembler_core.concat_funscript import (
    _build_parts_for_channel,
    _trim_funscript_window,
)
from forgeassembler_core.concat_video import build_ffmpeg_command
from forgeassembler_core.layout import lay_out
from forgeassembler_core.project import (
    Joiner,
    Output,
    Project,
    Segment,
    format_hms_ms,
    parse_hms_ms,
    split_segment_at,
    validate,
)


def _mp4(tmp: Path, name: str) -> Path:
    p = tmp / f"{name}.mp4"
    p.write_bytes(b"")
    return p


def _project(tmp: Path, *items, **overrides) -> Project:
    defaults = {"folder": str(tmp / "out"), "frame_rate": "30"}
    defaults.update(overrides)
    return Project(items=list(items), output=Output(**defaults))


# ── parse_hms_ms / format_hms_ms ──────────────────────────────────────
class TestParseHms:
    def test_full_hms_with_millis(self):
        assert parse_hms_ms("01:23:45.678") == (3600 + 23 * 60 + 45) * 1000 + 678

    def test_full_hms_no_millis(self):
        assert parse_hms_ms("01:00:00") == 3600 * 1000

    def test_minutes_seconds(self):
        assert parse_hms_ms("23:45") == (23 * 60 + 45) * 1000

    def test_minutes_seconds_with_millis(self):
        assert parse_hms_ms("00:30.500") == 30500

    def test_seconds_only(self):
        assert parse_hms_ms("45") == 45000

    def test_seconds_only_with_millis(self):
        assert parse_hms_ms("0.250") == 250

    def test_zero(self):
        assert parse_hms_ms("00:00:00.000") == 0
        assert parse_hms_ms("0") == 0

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            parse_hms_ms("")
        with pytest.raises(ValueError):
            parse_hms_ms("   ")

    def test_too_many_colons(self):
        with pytest.raises(ValueError):
            parse_hms_ms("1:2:3:4")

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            parse_hms_ms("-1")

    def test_minutes_over_60_rejected(self):
        with pytest.raises(ValueError):
            parse_hms_ms("00:61:00")

    def test_garbage_raises(self):
        with pytest.raises(ValueError):
            parse_hms_ms("abc")


class TestFormatHms:
    def test_zero(self):
        assert format_hms_ms(0) == "00:00:00.000"

    def test_subsecond(self):
        assert format_hms_ms(250) == "00:00:00.250"

    def test_minutes(self):
        assert format_hms_ms(90_000) == "00:01:30.000"

    def test_hours(self):
        assert format_hms_ms(3661_500) == "01:01:01.500"

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            format_hms_ms(-1)

    def test_round_trip(self):
        for ms in [0, 250, 1500, 60_000, 3600_000, 3725_678]:
            assert parse_hms_ms(format_hms_ms(ms)) == ms


# ── Segment trim accessors ────────────────────────────────────────────
class TestSegmentTrim:
    def test_no_trim_returns_zero_and_none(self):
        seg = Segment(id="s", video="x.mp4")
        assert seg.trim_start_ms() == 0
        assert seg.trim_end_ms() is None

    def test_trim_start_only(self):
        seg = Segment(id="s", video="x.mp4", trim_start="00:00:05.000")
        assert seg.trim_start_ms() == 5000
        assert seg.trim_end_ms() is None

    def test_trim_end_only(self):
        seg = Segment(id="s", video="x.mp4", trim_end="00:00:30.000")
        assert seg.trim_start_ms() == 0
        assert seg.trim_end_ms() == 30_000

    def test_trim_both(self):
        seg = Segment(
            id="s", video="x.mp4",
            trim_start="00:00:10.000", trim_end="00:00:30.000",
        )
        assert seg.trim_start_ms() == 10_000
        assert seg.trim_end_ms() == 30_000

    def test_effective_duration_no_trim(self):
        seg = Segment(id="s", video="x.mp4")
        assert seg.effective_duration_ms(60_000) == 60_000

    def test_effective_duration_with_trim(self):
        seg = Segment(
            id="s", video="x.mp4",
            trim_start="00:00:10.000", trim_end="00:00:30.000",
        )
        assert seg.effective_duration_ms(60_000) == 20_000

    def test_effective_duration_open_end(self):
        """trim_end unset -> use source duration as the end."""
        seg = Segment(id="s", video="x.mp4", trim_start="00:00:10.000")
        assert seg.effective_duration_ms(60_000) == 50_000


# ── layout honors trim ────────────────────────────────────────────────
class TestLayoutTrim:
    def test_untrimmed_uses_full_probe(self):
        p = Project(items=[Segment(id="s", video="a.mp4")])
        layout = lay_out(p, probe=lambda _p: 60_000)
        assert layout.total_duration_ms == 60_000

    def test_trimmed_segment_shorter_than_source(self):
        p = Project(items=[Segment(
            id="s", video="a.mp4",
            trim_start="00:00:10.000", trim_end="00:00:30.000",
        )])
        layout = lay_out(p, probe=lambda _p: 60_000)
        assert layout.total_duration_ms == 20_000

    def test_two_segments_one_trimmed(self):
        p = Project(items=[
            Segment(id="s1", video="a.mp4", trim_end="00:00:05.000"),
            Segment(id="s2", video="b.mp4"),
        ])
        layout = lay_out(p, probe=lambda _p: 10_000)
        # s1 contributes 5s, s2 contributes 10s
        assert layout.total_duration_ms == 15_000


# ── concat_video adds -ss/-t for trimmed segments ─────────────────────
class TestConcatVideoTrim:
    def test_untrimmed_segment_has_no_ss(self, tmp_path: Path):
        v = _mp4(tmp_path, "a")
        p = _project(tmp_path, Segment(id="s", video=str(v)))
        layout = lay_out(p, probe=lambda _p: 60_000)
        cmd = build_ffmpeg_command(p, layout)
        # The video input's pre_args should be empty.
        video_input = next(i for i in cmd.inputs if i.path == str(v))
        assert video_input.pre_args == []

    def test_trimmed_segment_emits_ss_and_t(self, tmp_path: Path):
        v = _mp4(tmp_path, "a")
        p = _project(tmp_path, Segment(
            id="s", video=str(v),
            trim_start="00:00:10.000", trim_end="00:00:30.000",
        ))
        layout = lay_out(p, probe=lambda _p: 60_000)
        cmd = build_ffmpeg_command(p, layout)
        video_input = next(i for i in cmd.inputs if i.path == str(v))
        # -ss before the seek time, -t before the duration
        assert "-ss" in video_input.pre_args
        ss_idx = video_input.pre_args.index("-ss")
        assert video_input.pre_args[ss_idx + 1] == "10"
        assert "-t" in video_input.pre_args
        t_idx = video_input.pre_args.index("-t")
        assert video_input.pre_args[t_idx + 1] == "20"

    def test_trim_start_only_emits_ss_and_t(self, tmp_path: Path):
        v = _mp4(tmp_path, "a")
        p = _project(tmp_path, Segment(
            id="s", video=str(v), trim_start="00:00:05.000",
        ))
        layout = lay_out(p, probe=lambda _p: 60_000)
        cmd = build_ffmpeg_command(p, layout)
        video_input = next(i for i in cmd.inputs if i.path == str(v))
        # trim_end unset -> read from 5s for the remaining 55s
        assert video_input.pre_args == ["-ss", "5", "-t", "55"]


# ── concat_funscript re-windows actions per trim ──────────────────────
class TestConcatFunscriptTrim:
    def test_untrimmed_passthrough(self):
        fs = {"actions": [{"at": 100, "pos": 50}, {"at": 500, "pos": 80}]}
        out = _trim_funscript_window(fs, 0, None)
        # Returned as-is when no trim is set.
        assert out is fs

    def test_drops_actions_before_window(self):
        fs = {"actions": [
            {"at": 100, "pos": 10},
            {"at": 500, "pos": 50},
            {"at": 1500, "pos": 90},
        ]}
        out = _trim_funscript_window(fs, 1000, None)
        # Only actions at >= 1000 survive, shifted by -1000.
        assert out["actions"] == [{"at": 500, "pos": 90}]

    def test_drops_actions_after_window(self):
        fs = {"actions": [
            {"at": 100, "pos": 10},
            {"at": 500, "pos": 50},
            {"at": 1500, "pos": 90},
        ]}
        out = _trim_funscript_window(fs, 0, 1000)
        # Actions strictly < 1000 survive (end is exclusive).
        assert out["actions"] == [
            {"at": 100, "pos": 10},
            {"at": 500, "pos": 50},
        ]

    def test_full_window_drop_and_shift(self):
        fs = {"actions": [
            {"at": 100, "pos": 10},
            {"at": 1100, "pos": 30},
            {"at": 1500, "pos": 50},
            {"at": 2500, "pos": 80},
        ]}
        out = _trim_funscript_window(fs, 1000, 2000)
        # Keep actions in [1000, 2000), shift by -1000.
        assert out["actions"] == [
            {"at": 100, "pos": 30},
            {"at": 500, "pos": 50},
        ]

    def test_actions_at_exact_boundaries(self):
        """Start is inclusive, end is exclusive — standard half-open."""
        fs = {"actions": [
            {"at": 1000, "pos": 10},  # at start: kept
            {"at": 2000, "pos": 20},  # at end: dropped
        ]}
        out = _trim_funscript_window(fs, 1000, 2000)
        assert out["actions"] == [{"at": 0, "pos": 10}]


class TestBuildPartsForChannelTrim:
    def test_part_uses_trimmed_duration_and_window(self, tmp_path: Path):
        """A trimmed segment's FunscriptPart has the trimmed duration
        AND only the in-window actions (already shifted to local time)."""
        # Set up a segment with a real funscript file so the resolver works.
        v = tmp_path / "clip.mp4"
        v.write_bytes(b"")
        fs_path = tmp_path / "clip.funscript"
        fs_path.write_text(
            '{"actions": ['
            '{"at": 500, "pos": 10},'
            '{"at": 5000, "pos": 50},'
            '{"at": 9500, "pos": 90}'
            ']}',
            encoding="utf-8",
        )
        seg = Segment(
            id="s", video=str(v),
            trim_start="00:00:03.000", trim_end="00:00:08.000",
        )
        p = _project(tmp_path, seg)
        layout = lay_out(p, probe=lambda _p: 10_000)
        parts = _build_parts_for_channel(p, layout, "main")
        assert len(parts) == 1
        part = parts[0]
        # Trimmed window = 5000ms
        assert part.duration_ms == 5000
        # Only the middle action survives, shifted by -3000
        assert part.funscript["actions"] == [{"at": 2000, "pos": 50}]


# ── split_segment_at ──────────────────────────────────────────────────
class TestSplitSegmentAt:
    def test_split_untrimmed_segment(self):
        seg = Segment(id="orig", video="x.mp4")
        head, tail = split_segment_at(seg, 30_000)
        assert head.id == "orig"
        assert head.trim_start is None  # untrimmed start preserved
        assert head.trim_end == "00:00:30.000"
        assert tail.id != "orig"
        assert tail.trim_start == "00:00:30.000"
        assert tail.trim_end is None
        # Both point at the same source video.
        assert head.video == tail.video == "x.mp4"

    def test_split_inside_existing_trim_window(self):
        seg = Segment(
            id="orig", video="x.mp4",
            trim_start="00:00:10.000", trim_end="00:00:50.000",
        )
        head, tail = split_segment_at(seg, 30_000)
        assert head.trim_start == "00:00:10.000"
        assert head.trim_end == "00:00:30.000"
        assert tail.trim_start == "00:00:30.000"
        assert tail.trim_end == "00:00:50.000"

    def test_split_at_or_before_start_raises(self):
        seg = Segment(id="orig", video="x.mp4", trim_start="00:00:10.000")
        with pytest.raises(ValueError):
            split_segment_at(seg, 10_000)
        with pytest.raises(ValueError):
            split_segment_at(seg, 5_000)

    def test_split_at_or_after_end_raises(self):
        seg = Segment(id="orig", video="x.mp4", trim_end="00:00:30.000")
        with pytest.raises(ValueError):
            split_segment_at(seg, 30_000)
        with pytest.raises(ValueError):
            split_segment_at(seg, 40_000)

    def test_split_still_image_raises(self):
        seg = Segment(id="orig", video="x.png", still_duration_s=5.0)
        with pytest.raises(ValueError):
            split_segment_at(seg, 1_000)

    def test_explicit_id_for_tail(self):
        seg = Segment(id="orig", video="x.mp4")
        head, tail = split_segment_at(seg, 5_000, new_segment_id="my-tail")
        assert head.id == "orig"
        assert tail.id == "my-tail"

    def test_overlays_travel_with_head(self):
        from forgeassembler_core.project import Overlay
        ov = Overlay(type="text", content="hello")
        seg = Segment(id="orig", video="x.mp4", overlays=[ov])
        head, tail = split_segment_at(seg, 5_000)
        assert len(head.overlays) == 1
        assert head.overlays[0] is not ov  # copied, not aliased
        assert head.overlays[0].content == "hello"
        assert tail.overlays == []

    def test_funscript_settings_copied(self):
        seg = Segment(
            id="orig", video="x.mp4",
            funscripts_source="explicit",
            explicit_funscripts={"main": "/path/main.funscript"},
        )
        head, tail = split_segment_at(seg, 5_000)
        assert head.funscripts_source == "explicit"
        assert head.explicit_funscripts == {"main": "/path/main.funscript"}
        assert tail.funscripts_source == "explicit"
        assert tail.explicit_funscripts == {"main": "/path/main.funscript"}
        # Dicts are copied so mutating one doesn't affect the other.
        head.explicit_funscripts["main"] = "/changed"
        assert tail.explicit_funscripts["main"] == "/path/main.funscript"


# ── validation ────────────────────────────────────────────────────────
class TestValidationTrim:
    def test_valid_trim_no_issues(self, tmp_path: Path):
        v = _mp4(tmp_path, "a")
        p = _project(tmp_path, Segment(
            id="s", video=str(v),
            trim_start="00:00:01.000", trim_end="00:00:05.000",
        ))
        issues = [i for i in validate(p) if i.level == "error"]
        assert issues == []

    def test_trim_start_geq_trim_end_is_error(self, tmp_path: Path):
        v = _mp4(tmp_path, "a")
        p = _project(tmp_path, Segment(
            id="s", video=str(v),
            trim_start="00:00:30.000", trim_end="00:00:10.000",
        ))
        errors = [i for i in validate(p) if i.level == "error"]
        assert any("trim_start" in i.message for i in errors)

    def test_invalid_trim_start_string_is_error(self, tmp_path: Path):
        v = _mp4(tmp_path, "a")
        p = _project(tmp_path, Segment(
            id="s", video=str(v), trim_start="garbage",
        ))
        errors = [i for i in validate(p) if i.level == "error"]
        assert any("Invalid trim_start" in i.message for i in errors)

    def test_still_with_trim_is_error(self, tmp_path: Path):
        png = tmp_path / "x.png"
        png.write_bytes(b"")
        p = _project(tmp_path, Segment(
            id="s", video=str(png),
            still_duration_s=5.0,
            trim_start="00:00:01.000",
        ))
        errors = [i for i in validate(p) if i.level == "error"]
        assert any("Still-image segments cannot be trimmed" in i.message for i in errors)


# ── end-to-end: layout + concat_video + concat_funscript with trim ────
class TestTrimEndToEnd:
    def test_two_trimmed_segments_compose(self, tmp_path: Path):
        v1 = _mp4(tmp_path, "a")
        v2 = _mp4(tmp_path, "b")
        # Two segments, both trimmed to 5s each => total 10s.
        p = _project(
            tmp_path,
            Segment(id="s1", video=str(v1),
                    trim_start="00:00:00.000", trim_end="00:00:05.000"),
            Joiner(id="j1", joiner_type="fade_to_black",
                   params={"duration_s": 1.0, "fade_s": 0.5}),
            Segment(id="s2", video=str(v2),
                    trim_start="00:00:10.000", trim_end="00:00:15.000"),
        )
        layout = lay_out(p, probe=lambda _p: 60_000)
        # 5s + 1s bridge + 5s
        assert layout.total_duration_ms == 11_000

        cmd = build_ffmpeg_command(p, layout)
        # Both video inputs carry -ss/-t pairs.
        v1_in = next(i for i in cmd.inputs if i.path == str(v1))
        v2_in = next(i for i in cmd.inputs if i.path == str(v2))
        assert v1_in.pre_args == ["-ss", "0", "-t", "5"]
        assert v2_in.pre_args == ["-ss", "10", "-t", "5"]
