# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Tests for build_ffmpeg_command — pure command builder.

No ffmpeg is invoked. These tests assert the declarative structure
(inputs, filter_complex fragments, map targets, output_args) of the
command the builder produces, driven by small fake layouts.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forgeassembler_core.concat_video import (
    FfmpegCommand,
    FfmpegInput,
    build_ffmpeg_command,
)
from forgeassembler_core.layout import lay_out
from forgeassembler_core.project import (
    AudioLayer,
    BugOverlay,
    Joiner,
    Output,
    OutputChannels,
    Project,
    Segment,
)


def _mp4(tmp: Path, name: str) -> Path:
    p = tmp / f"{name}.mp4"
    p.write_bytes(b"")
    return p


def _png(tmp: Path, name: str) -> Path:
    p = tmp / f"{name}.png"
    p.write_bytes(b"")
    return p


def _project(tmp: Path, *items, **output_overrides) -> Project:
    """Convenience: build a Project with a default output.folder."""
    defaults = {"folder": str(tmp / "out")}
    defaults.update(output_overrides)
    return Project(items=list(items), output=Output(**defaults))


# ── Basics / errors ───────────────────────────────────────────────────
def test_produce_video_false_raises(tmp_path: Path):
    v = _mp4(tmp_path, "a")
    p = _project(tmp_path, Segment(id="s1", video=str(v)), produce_video=False)
    layout = lay_out(p, probe=lambda _p: 1000)
    with pytest.raises(ValueError, match="produce_video is False"):
        build_ffmpeg_command(p, layout)


def test_no_segments_raises(tmp_path: Path):
    p = _project(tmp_path)
    layout = lay_out(p, probe=lambda _p: 1000)
    with pytest.raises(ValueError):
        build_ffmpeg_command(p, layout)


def test_source_resolution_requires_override(tmp_path: Path):
    v = _mp4(tmp_path, "a")
    p = _project(tmp_path, Segment(id="s1", video=str(v)), resolution="source")
    layout = lay_out(p, probe=lambda _p: 1000)
    with pytest.raises(ValueError, match="resolution_override"):
        build_ffmpeg_command(p, layout)


def test_source_resolution_honours_override(tmp_path: Path):
    v = _mp4(tmp_path, "a")
    p = _project(tmp_path, Segment(id="s1", video=str(v)), resolution="source")
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout, resolution_override=(1280, 720))
    assert "1280:720" in cmd.filter_complex


def test_output_path_derived_from_project(tmp_path: Path):
    v = _mp4(tmp_path, "a")
    p = _project(tmp_path, Segment(id="s1", video=str(v)))
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    assert cmd.output_path == str(tmp_path / "out" / "combined.mp4")


def test_output_path_override(tmp_path: Path):
    v = _mp4(tmp_path, "a")
    p = _project(tmp_path, Segment(id="s1", video=str(v)))
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout, output_path=str(tmp_path / "custom.mp4"))
    assert cmd.output_path == str(tmp_path / "custom.mp4")


def test_output_folder_missing_raises(tmp_path: Path):
    v = _mp4(tmp_path, "a")
    p = Project(items=[Segment(id="s1", video=str(v))])  # folder defaults None
    layout = lay_out(p, probe=lambda _p: 1000)
    with pytest.raises(ValueError, match="output.folder is required"):
        build_ffmpeg_command(p, layout)


# ── Single-segment command structure ──────────────────────────────────
def test_single_segment_basic(tmp_path: Path):
    v = _mp4(tmp_path, "a")
    p = _project(tmp_path, Segment(id="s1", video=str(v)))
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)

    assert len(cmd.inputs) == 1
    assert cmd.inputs[0].path == str(v)
    assert cmd.inputs[0].pre_args == []

    fc = cmd.filter_complex
    assert "[0:v]scale=1920:1080" in fc
    assert "pad=1920:1080" in fc
    # Only one segment → no concat filter
    assert "concat=n=" not in fc


def test_single_segment_no_concat_needed(tmp_path: Path):
    """With one segment, the map labels point at the per-segment
    streams, not at a concat output."""
    v = _mp4(tmp_path, "a")
    p = _project(tmp_path, Segment(id="s1", video=str(v)), normalize_audio=False)
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)

    # Neither map should reference a 'vconcat' / 'aconcat' label.
    assert "vconcat" not in (cmd.map_video or "")
    assert "aconcat" not in (cmd.map_audio or "")


# ── Two segments, none joiner ─────────────────────────────────────────
def test_two_segments_none_joiner(tmp_path: Path):
    v1 = _mp4(tmp_path, "a")
    v2 = _mp4(tmp_path, "b")
    p = _project(
        tmp_path,
        Segment(id="s1", video=str(v1)),
        Joiner(id="j1", joiner_type="none"),
        Segment(id="s2", video=str(v2)),
        normalize_audio=False,
    )
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)

    assert len(cmd.inputs) == 2
    fc = cmd.filter_complex
    # Two segments → concat=n=2
    assert "concat=n=2:v=1:a=1" in fc
    # No black bridge
    assert "color=c=black" not in fc


# ── Fade-to-black joiner: bridge + fades ──────────────────────────────
def test_fade_to_black_inserts_black_bridge(tmp_path: Path):
    v1 = _mp4(tmp_path, "a")
    v2 = _mp4(tmp_path, "b")
    p = _project(
        tmp_path,
        Segment(id="s1", video=str(v1)),
        Joiner(id="j1", joiner_type="fade_to_black", params={"duration_s": 2.0}),
        Segment(id="s2", video=str(v2)),
        normalize_audio=False,
    )
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)

    fc = cmd.filter_complex
    # Solid black bridge of exactly the joiner duration
    assert "color=c=black:s=1920x1080:d=2" in fc
    # Silence for the bridge audio
    assert "anullsrc=d=2:r=48000:cl=stereo" in fc
    # Concat should be n=3 (seg + bridge + seg)
    assert "concat=n=3:v=1:a=1" in fc


def test_fade_to_black_adds_fade_filters_to_adjacent_segments(tmp_path: Path):
    v1 = _mp4(tmp_path, "a")
    v2 = _mp4(tmp_path, "b")
    p = _project(
        tmp_path,
        Segment(id="s1", video=str(v1)),
        Joiner(id="j1", joiner_type="fade_to_black", params={"duration_s": 1.0}),
        Segment(id="s2", video=str(v2)),
        normalize_audio=False,
    )
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    fc = cmd.filter_complex

    # Tail fade on seg 0 video + audio: fade_s = 0.5 (joiner/2)
    assert "fade=t=out:st=0.5:d=0.5" in fc
    assert "afade=t=out:st=0.5:d=0.5" in fc
    # Head fade on seg 1 video + audio
    assert "fade=t=in:st=0:d=0.5" in fc
    assert "afade=t=in:st=0:d=0.5" in fc


def test_fade_duration_capped_at_half_second(tmp_path: Path):
    v1 = _mp4(tmp_path, "a")
    v2 = _mp4(tmp_path, "b")
    # Big fade: 4 seconds. Per-side fade should be clamped to 0.5s.
    p = _project(
        tmp_path,
        Segment(id="s1", video=str(v1)),
        Joiner(id="j1", joiner_type="fade_to_black", params={"duration_s": 4.0}),
        Segment(id="s2", video=str(v2)),
        normalize_audio=False,
    )
    layout = lay_out(p, probe=lambda _p: 2000)
    cmd = build_ffmpeg_command(p, layout)
    fc = cmd.filter_complex
    # Tail fade starts at 2 - 0.5 = 1.5, duration 0.5
    assert "fade=t=out:st=1.5:d=0.5" in fc


def test_three_segments_mixed_joiners(tmp_path: Path):
    v1, v2, v3 = [_mp4(tmp_path, n) for n in ("a", "b", "c")]
    p = _project(
        tmp_path,
        Segment(id="s1", video=str(v1)),
        Joiner(id="j1", joiner_type="none"),
        Segment(id="s2", video=str(v2)),
        Joiner(id="j2", joiner_type="fade_to_black", params={"duration_s": 1.0}),
        Segment(id="s3", video=str(v3)),
        normalize_audio=False,
    )
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    fc = cmd.filter_complex
    # 3 segments + 1 bridge (from fade_to_black) = 4 streams concatenated
    assert "concat=n=4:v=1:a=1" in fc


# ── Still images ──────────────────────────────────────────────────────
def test_still_image_segment_loops_with_duration(tmp_path: Path):
    png = _png(tmp_path, "card")
    p = _project(
        tmp_path,
        Segment(id="s1", video=str(png), still_duration_s=3.0),
        normalize_audio=False,
    )
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)

    assert cmd.inputs[0].pre_args == ["-loop", "1", "-t", "3"]
    # Stills get silence regardless of audio mode
    assert "anullsrc=d=3:r=48000:cl=stereo" in cmd.filter_complex


def test_still_image_with_replacement_audio(tmp_path: Path):
    png = _png(tmp_path, "card")
    mp3 = tmp_path / "voice.mp3"
    mp3.write_bytes(b"")
    p = _project(
        tmp_path,
        Segment(
            id="s1",
            video=str(png),
            still_duration_s=2.5,
            audio=AudioLayer(mode="replace", file=str(mp3)),
        ),
        normalize_audio=False,
    )
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)

    # Two inputs: the PNG (looped) and the replacement audio (also -t capped)
    assert len(cmd.inputs) == 2
    assert cmd.inputs[0].pre_args == ["-loop", "1", "-t", "2.5"]
    assert cmd.inputs[1].pre_args == ["-t", "2.5"]


# ── Audio modes ───────────────────────────────────────────────────────
def test_audio_mode_silence(tmp_path: Path):
    v = _mp4(tmp_path, "a")
    p = _project(
        tmp_path,
        Segment(id="s1", video=str(v), audio=AudioLayer(mode="silence")),
        normalize_audio=False,
    )
    layout = lay_out(p, probe=lambda _p: 1500)
    cmd = build_ffmpeg_command(p, layout)
    assert "anullsrc=d=1.5:r=48000:cl=stereo" in cmd.filter_complex


def test_audio_mode_keep_uses_input_audio(tmp_path: Path):
    v = _mp4(tmp_path, "a")
    p = _project(tmp_path, Segment(id="s1", video=str(v)), normalize_audio=False)
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    assert "[0:a]aresample=48000" in cmd.filter_complex


def test_audio_mode_replace_adds_audio_input(tmp_path: Path):
    v = _mp4(tmp_path, "a")
    mp3 = tmp_path / "voice.mp3"
    mp3.write_bytes(b"")
    p = _project(
        tmp_path,
        Segment(
            id="s1", video=str(v),
            audio=AudioLayer(mode="replace", file=str(mp3)),
        ),
        normalize_audio=False,
    )
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    assert len(cmd.inputs) == 2
    assert cmd.inputs[1].path == str(mp3)
    # The second input's audio, not the first segment's, is routed to the segment
    assert "[1:a]aresample=48000" in cmd.filter_complex


def test_audio_mode_replace_missing_file_raises(tmp_path: Path):
    v = _mp4(tmp_path, "a")
    p = _project(
        tmp_path,
        Segment(id="s1", video=str(v), audio=AudioLayer(mode="replace", file=None)),
    )
    layout = lay_out(p, probe=lambda _p: 1000)
    with pytest.raises(ValueError, match="audio.file missing"):
        build_ffmpeg_command(p, layout)


# ── Bug overlay ───────────────────────────────────────────────────────
def test_bug_overlay_adds_input_and_filter(tmp_path: Path):
    v = _mp4(tmp_path, "a")
    bug = tmp_path / "bug.png"
    bug.write_bytes(b"")
    p = _project(
        tmp_path,
        Segment(id="s1", video=str(v)),
        bug=BugOverlay(file=str(bug), corner="br", margin_px=20, opacity=0.7),
        normalize_audio=False,
    )
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)

    # Extra input for the bug, with -loop and -t matching total duration
    assert any(
        inp.path == str(bug) and "-loop" in inp.pre_args
        for inp in cmd.inputs
    )
    fc = cmd.filter_complex
    assert "format=rgba,colorchannelmixer=aa=0.7" in fc
    # Overlay positions at bottom-right with margin
    assert "overlay=x=W-w-20:y=H-h-20" in fc
    assert cmd.map_video == "[v_bugged]"


def test_bug_overlay_absent_by_default(tmp_path: Path):
    v = _mp4(tmp_path, "a")
    p = _project(tmp_path, Segment(id="s1", video=str(v)), normalize_audio=False)
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    assert "v_bugged" not in cmd.filter_complex
    assert "bug_rgba" not in cmd.filter_complex


# ── Normalize audio / color temperature ───────────────────────────────
def test_normalize_audio_adds_loudnorm(tmp_path: Path):
    v = _mp4(tmp_path, "a")
    p = _project(tmp_path, Segment(id="s1", video=str(v)))  # default normalize=True
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    assert "loudnorm=I=-16:TP=-1.5:LRA=11" in cmd.filter_complex
    assert cmd.map_audio == "[a_loud]"


def test_normalize_audio_off_skips_loudnorm(tmp_path: Path):
    v = _mp4(tmp_path, "a")
    p = _project(tmp_path, Segment(id="s1", video=str(v)), normalize_audio=False)
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    assert "loudnorm" not in cmd.filter_complex


def test_color_temperature_applied_to_segment(tmp_path: Path):
    v = _mp4(tmp_path, "a")
    p = _project(
        tmp_path,
        Segment(id="s1", video=str(v), color_temperature_k=6200),
        normalize_audio=False,
    )
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    assert "colortemperature=temperature=6200" in cmd.filter_complex


# ── Resolution dropdown ───────────────────────────────────────────────
@pytest.mark.parametrize("key,w,h", [
    ("1080p",     1920, 1080),
    ("1440p",     2560, 1440),
    ("4k",        3840, 2160),
    ("uw_1080p",  2560, 1080),
    ("uw_1440p",  3440, 1440),
    ("4_3_hd",    1440, 1080),
    ("3_4_hd",    1080, 1440),
    ("9_16_hd",   1080, 1920),
])
def test_all_resolution_keys_scale_correctly(tmp_path: Path, key, w, h):
    v = _mp4(tmp_path, "a")
    p = _project(tmp_path, Segment(id="s1", video=str(v)), resolution=key)
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    assert f"scale={w}:{h}" in cmd.filter_complex
    # Padding + concat colorspace both reference the same dims
    assert f"pad={w}:{h}" in cmd.filter_complex


# ── FfmpegCommand.to_argv ─────────────────────────────────────────────
def test_to_argv_round_trip(tmp_path: Path):
    v = _mp4(tmp_path, "a")
    p = _project(tmp_path, Segment(id="s1", video=str(v)), normalize_audio=False)
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    argv = cmd.to_argv("/opt/ffmpeg")
    assert argv[0] == "/opt/ffmpeg"
    assert "-i" in argv
    assert str(v) in argv
    assert "-filter_complex" in argv
    assert "-y" in argv
    assert argv[-1] == cmd.output_path
    # Map directives present
    i_map = argv.index("-map")
    assert argv[i_map + 1] == cmd.map_video


def test_to_argv_renders_all_input_pre_args(tmp_path: Path):
    png = _png(tmp_path, "card")
    p = _project(
        tmp_path,
        Segment(id="s1", video=str(png), still_duration_s=2.0),
        normalize_audio=False,
    )
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    argv = cmd.to_argv("ffmpeg")
    assert "-loop" in argv
    assert "-t" in argv


# ── Output args ───────────────────────────────────────────────────────
def test_output_args_include_h264_and_aac(tmp_path: Path):
    v = _mp4(tmp_path, "a")
    p = _project(tmp_path, Segment(id="s1", video=str(v)))
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    assert "libx264" in cmd.output_args
    assert "aac" in cmd.output_args
    assert "yuv420p" in cmd.output_args
