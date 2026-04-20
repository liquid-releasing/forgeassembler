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
    Metadata,
    Output,
    OutputChannels,
    Project,
    Section,
    SectionOverlay,
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
    """Convenience: build a Project with a default output.folder.

    Defaults `frame_rate` to `"30"` so build_ffmpeg_command doesn't
    require a probe. Tests that need to exercise `"source"` supply it
    explicitly.
    """
    defaults = {"folder": str(tmp / "out"), "frame_rate": "30"}
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
    # No solid-colour bridge
    assert "color=c=0x" not in fc


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
    assert "color=c=0x000000:s=1920x1080:d=2" in fc
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


def test_audio_mode_keep_falls_back_to_silence_when_no_audio_stream(
    tmp_path: Path,
):
    """Phone captures / silent animations may have no audio stream at
    all. When the caller signals that via `segments_with_audio` (empty
    set → this clip has no audio), the pipeline should emit anullsrc
    instead of referencing a missing `[N:a]` stream."""
    v = _mp4(tmp_path, "a")
    p = _project(tmp_path, Segment(id="s1", video=str(v)), normalize_audio=False)
    layout = lay_out(p, probe=lambda _p: 2000)
    cmd = build_ffmpeg_command(p, layout, segments_with_audio=set())
    assert "anullsrc=d=2:r=48000:cl=stereo[a_base0]" in cmd.filter_complex
    assert "[0:a]aresample" not in cmd.filter_complex


def test_audio_mode_keep_default_assumes_audio_present(tmp_path: Path):
    """Back-compat: when `segments_with_audio` is None, we assume every
    keep-mode segment has audio (tests that predate the audio probe
    still pass without wiring)."""
    v = _mp4(tmp_path, "a")
    p = _project(tmp_path, Segment(id="s1", video=str(v)), normalize_audio=False)
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)  # default segments_with_audio=None
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
    # Non-still replacement audio should also be -t truncated to the segment
    # duration (1 second in this test).
    assert cmd.inputs[1].pre_args == ["-t", "1"]


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


# ── Quality preset → CRF ──────────────────────────────────────────────
def test_quality_default_emits_crf_23(tmp_path: Path):
    """Default quality ('medium') maps to CRF 23 in the ffmpeg args."""
    v = _mp4(tmp_path, "a")
    p = _project(tmp_path, Segment(id="s1", video=str(v)))
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    crf_idx = cmd.output_args.index("-crf")
    assert cmd.output_args[crf_idx + 1] == "23"


def test_quality_high_emits_crf_18(tmp_path: Path):
    v = _mp4(tmp_path, "a")
    p = _project(tmp_path, Segment(id="s1", video=str(v)), quality="high")
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    crf_idx = cmd.output_args.index("-crf")
    assert cmd.output_args[crf_idx + 1] == "18"


def test_quality_low_emits_crf_28(tmp_path: Path):
    v = _mp4(tmp_path, "a")
    p = _project(tmp_path, Segment(id="s1", video=str(v)), quality="low")
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    crf_idx = cmd.output_args.index("-crf")
    assert cmd.output_args[crf_idx + 1] == "28"


# ── Frame rate ────────────────────────────────────────────────────────
@pytest.mark.parametrize("key,expected", [
    ("24", "24"),
    ("30", "30"),
    ("60", "60"),
])
def test_frame_rate_fixed_value_emits_matching_r(tmp_path: Path, key, expected):
    v = _mp4(tmp_path, "a")
    p = _project(tmp_path, Segment(id="s1", video=str(v)), frame_rate=key)
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    r_idx = cmd.output_args.index("-r")
    assert cmd.output_args[r_idx + 1] == expected


def test_frame_rate_source_requires_override(tmp_path: Path):
    v = _mp4(tmp_path, "a")
    p = _project(tmp_path, Segment(id="s1", video=str(v)), frame_rate="source")
    layout = lay_out(p, probe=lambda _p: 1000)
    with pytest.raises(ValueError, match="frame_rate_override"):
        build_ffmpeg_command(p, layout)


def test_frame_rate_source_honours_override(tmp_path: Path):
    v = _mp4(tmp_path, "a")
    p = _project(tmp_path, Segment(id="s1", video=str(v)), frame_rate="source")
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout, frame_rate_override=60)
    r_idx = cmd.output_args.index("-r")
    assert cmd.output_args[r_idx + 1] == "60"


def test_frame_rate_override_wins_over_fixed(tmp_path: Path):
    """Explicit override from caller beats the project's fixed value
    (lets callers force a specific fps from the CLI / tests)."""
    v = _mp4(tmp_path, "a")
    p = _project(tmp_path, Segment(id="s1", video=str(v)), frame_rate="30")
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout, frame_rate_override=24)
    r_idx = cmd.output_args.index("-r")
    assert cmd.output_args[r_idx + 1] == "24"


def test_frame_rate_reaches_color_bridge(tmp_path: Path):
    """Fade-to-black bridge source uses the same fps as the encoder."""
    v1 = _mp4(tmp_path, "a")
    v2 = _mp4(tmp_path, "b")
    p = _project(
        tmp_path,
        Segment(id="s1", video=str(v1)),
        Joiner(id="j1", joiner_type="fade_to_black",
               params={"duration_s": 1.0}),
        Segment(id="s2", video=str(v2)),
        frame_rate="60",
        normalize_audio=False,
    )
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    # Bridge color source declares its own frame rate.
    assert ":r=60" in cmd.filter_complex


# ── Metadata ──────────────────────────────────────────────────────────
def test_output_always_tags_encoder(tmp_path: Path):
    v = _mp4(tmp_path, "a")
    p = _project(tmp_path, Segment(id="s1", video=str(v)))
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    # `encoder` is auto-set even without user metadata
    encoder_idx = cmd.output_args.index("-metadata") if "-metadata" in cmd.output_args else -1
    assert encoder_idx != -1
    # Find any arg that starts with 'encoder='
    assert any(
        a.startswith("encoder=ForgeAssembler") for a in cmd.output_args
    )


def test_output_emits_user_metadata(tmp_path: Path):
    v = _mp4(tmp_path, "a")
    p = _project(
        tmp_path,
        Segment(id="s1", video=str(v)),
        metadata=Metadata(
            title="Wild Ride", artist="Liquid Releasing",
            date="2026", genre="Haptic",
        ),
    )
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    args = cmd.output_args
    assert "title=Wild Ride" in args
    assert "artist=Liquid Releasing" in args
    assert "date=2026" in args
    assert "genre=Haptic" in args


def test_output_metadata_omits_empty(tmp_path: Path):
    v = _mp4(tmp_path, "a")
    p = _project(
        tmp_path,
        Segment(id="s1", video=str(v)),
        metadata=Metadata(title="Only A Title"),
    )
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    # Should not emit metadata for fields that were left None
    assert not any(a.startswith("artist=") for a in cmd.output_args)
    assert not any(a.startswith("date=") for a in cmd.output_args)
    assert any(a == "title=Only A Title" for a in cmd.output_args)


def test_output_metadata_to_argv_preserves_pairs(tmp_path: Path):
    """Ensure the rendered argv has `-metadata key=value` structure."""
    v = _mp4(tmp_path, "a")
    p = _project(
        tmp_path,
        Segment(id="s1", video=str(v)),
        metadata=Metadata(title="T"),
    )
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    argv = cmd.to_argv("ffmpeg")
    # Find the title pair
    for i, a in enumerate(argv):
        if a == "-metadata" and i + 1 < len(argv) and argv[i + 1] == "title=T":
            return  # success
    raise AssertionError(
        f"Did not find -metadata title=T pair in argv: {argv}",
    )


# ── fade_to_black colour parameter ────────────────────────────────────
def test_fade_to_black_default_color_is_black(tmp_path: Path):
    v1 = _mp4(tmp_path, "a")
    v2 = _mp4(tmp_path, "b")
    p = _project(
        tmp_path,
        Segment(id="s1", video=str(v1)),
        Joiner(id="j1", joiner_type="fade_to_black",
               params={"duration_s": 2.0}),
        Segment(id="s2", video=str(v2)),
        normalize_audio=False,
    )
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    assert "color=c=0x000000" in cmd.filter_complex


def test_fade_to_black_accepts_custom_color(tmp_path: Path):
    v1 = _mp4(tmp_path, "a")
    v2 = _mp4(tmp_path, "b")
    p = _project(
        tmp_path,
        Segment(id="s1", video=str(v1)),
        Joiner(
            id="j1", joiner_type="fade_to_black",
            params={"duration_s": 2.0, "color": "#1a1a1a"},
        ),
        Segment(id="s2", video=str(v2)),
        normalize_audio=False,
    )
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    assert "color=c=0x1a1a1a" in cmd.filter_complex


def test_fade_to_black_color_accepts_no_hash(tmp_path: Path):
    v1 = _mp4(tmp_path, "a")
    v2 = _mp4(tmp_path, "b")
    p = _project(
        tmp_path,
        Segment(id="s1", video=str(v1)),
        Joiner(
            id="j1", joiner_type="fade_to_black",
            params={"duration_s": 2.0, "color": "2a2a2a"},
        ),
        Segment(id="s2", video=str(v2)),
        normalize_audio=False,
    )
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    assert "color=c=0x2a2a2a" in cmd.filter_complex


def test_fade_to_black_color_falls_back_on_invalid(tmp_path: Path):
    v1 = _mp4(tmp_path, "a")
    v2 = _mp4(tmp_path, "b")
    p = _project(
        tmp_path,
        Segment(id="s1", video=str(v1)),
        Joiner(
            id="j1", joiner_type="fade_to_black",
            params={"duration_s": 2.0, "color": "not a color"},
        ),
        Segment(id="s2", video=str(v2)),
        normalize_audio=False,
    )
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    # Falls back to black
    assert "color=c=0x000000" in cmd.filter_complex


# ── Per-segment image overlays ────────────────────────────────────────
def test_segment_overlay_registers_input_and_composites(tmp_path: Path):
    from forgeassembler_core.project import Overlay

    v = _mp4(tmp_path, "a")
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"")
    p = _project(
        tmp_path,
        Segment(
            id="s1", video=str(v),
            overlays=[Overlay(
                type="image", file=str(logo),
                position="bottom-left",
                start_s=0.0,
            )],
        ),
        normalize_audio=False,
    )
    layout = lay_out(p, probe=lambda _p: 2000)
    cmd = build_ffmpeg_command(p, layout)
    # Logo PNG registered as its own looped input with segment duration
    assert any(inp.path == str(logo) for inp in cmd.inputs)
    assert cmd.inputs[1].pre_args == ["-loop", "1", "-t", "2"]
    # Overlay composite appears in the graph
    assert "v_ov_0_0" in cmd.filter_complex
    assert "overlay=x=0:y=H-h" in cmd.filter_complex


def test_segment_overlay_fade_in(tmp_path: Path):
    from forgeassembler_core.project import Overlay

    v = _mp4(tmp_path, "a")
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"")
    p = _project(
        tmp_path,
        Segment(
            id="s1", video=str(v),
            overlays=[Overlay(
                type="image", file=str(logo),
                position="bottom-left",
                start_s=3.0,
                fade_in_s=5.0,
            )],
        ),
        normalize_audio=False,
    )
    layout = lay_out(p, probe=lambda _p: 10000)
    cmd = build_ffmpeg_command(p, layout)
    # fade-in on the overlay starts at its start_s for fade_in_s seconds
    assert "fade=t=in:st=3:d=5:alpha=1" in cmd.filter_complex


def test_segment_overlay_time_window(tmp_path: Path):
    from forgeassembler_core.project import Overlay

    v = _mp4(tmp_path, "a")
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"")
    p = _project(
        tmp_path,
        Segment(
            id="s1", video=str(v),
            overlays=[Overlay(
                type="image", file=str(logo),
                position="bottom-right",
                start_s=1.0,
                end_s=4.0,
                fade_in_s=0.5,
                fade_out_s=0.5,
            )],
        ),
        normalize_audio=False,
    )
    layout = lay_out(p, probe=lambda _p: 5000)
    cmd = build_ffmpeg_command(p, layout)
    fc = cmd.filter_complex
    assert "fade=t=in:st=1:d=0.5:alpha=1" in fc
    assert "fade=t=out:st=3.5:d=0.5:alpha=1" in fc
    assert "enable='between(t,1,4)'" in fc


def test_text_overlays_skipped_in_v1(tmp_path: Path):
    """Text overlays are in the schema but deferred to a later phase;
    they shouldn't add inputs or filters to the command."""
    from forgeassembler_core.project import Overlay

    v = _mp4(tmp_path, "a")
    p = _project(
        tmp_path,
        Segment(
            id="s1", video=str(v),
            overlays=[Overlay(type="text", content="hello", size=48)],
        ),
        normalize_audio=False,
    )
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    # Only one input: the segment video itself
    assert len(cmd.inputs) == 1
    # No overlay composite in the graph
    assert "v_ov_" not in cmd.filter_complex


def test_multiple_overlays_chain_in_order(tmp_path: Path):
    from forgeassembler_core.project import Overlay

    v = _mp4(tmp_path, "a")
    logo = tmp_path / "logo.png"; logo.write_bytes(b"")
    caption = tmp_path / "cap.png"; caption.write_bytes(b"")
    p = _project(
        tmp_path,
        Segment(
            id="s1", video=str(v),
            overlays=[
                Overlay(type="image", file=str(logo),
                        position="bottom-left"),
                Overlay(type="image", file=str(caption),
                        position="top-center", start_s=2.0),
            ],
        ),
        normalize_audio=False,
    )
    layout = lay_out(p, probe=lambda _p: 5000)
    cmd = build_ffmpeg_command(p, layout)
    fc = cmd.filter_complex
    # Two overlay labels are emitted in order
    assert "v_ov_0_0" in fc
    assert "v_ov_0_1" in fc
    # Second overlay chains onto first
    assert "[v_ov_0_0]" in fc or "v_ov_0_0][" in fc.replace(" ", "")


# ── previous_last_frame background ────────────────────────────────────
def _title_project(tmp_path: Path) -> tuple[Project, str, str]:
    """Build a Project with a video segment followed by a PNG title
    segment that uses background=previous_last_frame. Returns
    (project, video_path, png_path) so tests can refer to input paths."""
    v = _mp4(tmp_path, "clip")
    png = _png(tmp_path, "title")
    p = _project(
        tmp_path,
        Segment(id="s_video", video=str(v)),
        Segment(
            id="s_title", video=str(png),
            still_duration_s=2.0,
            background="previous_last_frame",
        ),
        normalize_audio=False,
    )
    return p, str(v), str(png)


def test_previous_last_frame_without_cache_raises(tmp_path: Path):
    p, _v, _png = _title_project(tmp_path)
    layout = lay_out(p, probe=lambda _p: 1000)
    with pytest.raises(ValueError, match="frame_cache"):
        build_ffmpeg_command(p, layout)


def test_previous_last_frame_adds_background_input(tmp_path: Path):
    p, _v, png = _title_project(tmp_path)
    layout = lay_out(p, probe=lambda _p: 1000)
    extracted = str(tmp_path / "extracted.png")
    cmd = build_ffmpeg_command(
        p, layout, frame_cache={"s_title": extracted},
    )
    # Inputs: seg 0 video, seg 1 PNG (foreground), extracted frame (background)
    paths = [inp.path for inp in cmd.inputs]
    assert str(tmp_path / "clip.mp4") in paths
    assert png in paths
    assert extracted in paths


def test_previous_last_frame_emits_overlay_composite(tmp_path: Path):
    p, _v, _png = _title_project(tmp_path)
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(
        p, layout, frame_cache={"s_title": "/tmp/extracted.png"},
    )
    fc = cmd.filter_complex
    # Background normalized to canonical size
    assert "v_bg1" in fc
    # Composite: bg + fg → v_composed
    assert "v_composed1" in fc
    # The composite uses overlay with center positioning
    assert "overlay=x=(W-w)/2:y=(H-h)/2:format=auto" in fc


def test_previous_last_frame_color_temperature_applies_after_composite(
    tmp_path: Path,
):
    v = _mp4(tmp_path, "clip")
    png = _png(tmp_path, "title")
    p = _project(
        tmp_path,
        Segment(id="s_video", video=str(v)),
        Segment(
            id="s_title", video=str(png),
            still_duration_s=1.5,
            background="previous_last_frame",
            color_temperature_k=5500,
        ),
        normalize_audio=False,
    )
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(
        p, layout, frame_cache={"s_title": "/tmp/frame.png"},
    )
    fc = cmd.filter_complex
    # Color temperature applied to the composed output, not to the bg input
    assert "[v_composed1]colortemperature=temperature=5500" in fc


def test_previous_last_frame_preserves_other_segment_path(tmp_path: Path):
    """The preceding real video segment should still normalize via
    the single-input path, not the composite path."""
    p, _v, _png = _title_project(tmp_path)
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(
        p, layout, frame_cache={"s_title": "/tmp/frame.png"},
    )
    # seg 0 uses v_norm0 directly from its input (no v_bg0 or v_composed0)
    assert "v_bg0" not in cmd.filter_complex
    assert "v_composed0" not in cmd.filter_complex


def test_previous_last_frame_audio_is_silence(tmp_path: Path):
    """PNG title segment's audio remains silence (stills always)."""
    p, _v, _png = _title_project(tmp_path)
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(
        p, layout, frame_cache={"s_title": "/tmp/frame.png"},
    )
    # Two audio base labels: a_base0 (keep from seg 0 real video),
    # a_base1 (silence for still)
    assert "anullsrc=d=2:r=48000:cl=stereo[a_base1]" in cmd.filter_complex


# ── Section-level image overlays (Phase B) ────────────────────────────
def _section_project(tmp_path: Path) -> tuple[Project, Path, Path]:
    """Build a 2-section project and return (project, v1_path, v2_path).

    v1 is in section 1, v2 is in section 2. Each section has one clip
    so test code can attach overlays and inspect the rendered filters.
    """
    v1 = _mp4(tmp_path, "a")
    v2 = _mp4(tmp_path, "b")
    project = Project(
        sections=[
            Section(id="sec1", segments=[Segment(id="s1", video=str(v1))]),
            Section(id="sec2", segments=[Segment(id="s2", video=str(v2))]),
        ],
        output=Output(
            folder=str(tmp_path / "out"),
            frame_rate="30",
            normalize_audio=False,
        ),
    )
    return project, v1, v2


def test_section_image_overlay_adds_input(tmp_path: Path):
    p, _v1, _v2 = _section_project(tmp_path)
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"")
    p.sections[1].overlays.append(SectionOverlay(
        id="ov1", kind="image", file=str(logo),
        start_s=0.5, duration_s=1.0, position="br", opacity=0.9,
    ))
    layout = lay_out(p, probe=lambda _p: 2000)
    cmd = build_ffmpeg_command(p, layout)

    # Extra input registered for the overlay PNG, looped to its own
    # effective duration.
    matches = [
        inp for inp in cmd.inputs
        if inp.path == str(logo) and "-loop" in inp.pre_args
    ]
    assert matches, "overlay PNG should be registered as a looped input"


def test_section_image_overlay_input_lives_until_enable_window_ends(
    tmp_path: Path,
):
    """Regression: the image input's `-t` must cover [0, abs_end_s],
    not just [0, effective_dur]. Otherwise, for any section that isn't
    the first, the looped image stream ends long before the overlay's
    enable window opens and the image never appears.

    Section 1 = 0..2s, Section 2 = 2..4s. Overlay on sec 2 with
    start_s=0.5, duration_s=1.0 → abs_end_s = 3.5. The input's `-t`
    must be 3.5, not 1.0.
    """
    p, _v1, _v2 = _section_project(tmp_path)
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"")
    p.sections[1].overlays.append(SectionOverlay(
        id="ov1", kind="image", file=str(logo),
        start_s=0.5, duration_s=1.0, position="center",
    ))
    layout = lay_out(p, probe=lambda _p: 2000)
    cmd = build_ffmpeg_command(p, layout)
    matches = [
        inp for inp in cmd.inputs
        if inp.path == str(logo) and "-loop" in inp.pre_args
    ]
    assert matches, "overlay PNG should be registered as a looped input"
    # pre_args is ["-loop", "1", "-t", "<value>"]
    t_idx = matches[0].pre_args.index("-t")
    t_value = float(matches[0].pre_args[t_idx + 1])
    assert t_value == 3.5, (
        f"expected -t 3.5 (abs_end_s) so the image stream is alive when "
        f"enable opens at abs_start_s=2.5; got {t_value}"
    )


def test_section_image_overlay_uses_section_absolute_times(tmp_path: Path):
    """Overlay start_s is relative to the SECTION; in the final graph
    it translates to an absolute timeline time (section_start +
    start_s). Section 1 covers 0-2s; Section 2 covers 2-4s. An overlay
    with start_s=0.5s on section 2 should render enable='between(t,2.5,...'."""
    p, _v1, _v2 = _section_project(tmp_path)
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"")
    p.sections[1].overlays.append(SectionOverlay(
        id="ov1", kind="image", file=str(logo),
        start_s=0.5, duration_s=1.0, position="center",
    ))
    layout = lay_out(p, probe=lambda _p: 2000)
    cmd = build_ffmpeg_command(p, layout)
    fc = cmd.filter_complex
    assert "enable='between(t,2.5,3.5)'" in fc


def test_section_image_overlay_default_duration_runs_to_section_end(tmp_path: Path):
    """duration_s == 0 means 'to the end of the section' — this lets
    users say 'show this logo for the whole section' without typing
    the math."""
    p, _v1, _v2 = _section_project(tmp_path)
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"")
    p.sections[0].overlays.append(SectionOverlay(
        id="ov1", kind="image", file=str(logo),
        start_s=0.0, duration_s=0.0,  # full section
    ))
    layout = lay_out(p, probe=lambda _p: 3000)
    cmd = build_ffmpeg_command(p, layout)
    # Section 1 covers 0-3s; overlay should enable over that range.
    assert "enable='between(t,0,3)'" in cmd.filter_complex


def test_section_image_overlay_position_shortcuts(tmp_path: Path):
    """Short codes tl/tr/bl/br map to the same corner expressions as
    the bug overlay uses."""
    p, _v1, _v2 = _section_project(tmp_path)
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"")
    p.sections[0].overlays.append(SectionOverlay(
        id="ov1", kind="image", file=str(logo), position="br",
    ))
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    # Bottom-right places overlay at (W-w, H-h)
    assert "overlay=x=W-w:y=H-h" in cmd.filter_complex


def test_multiple_section_overlays_stack_in_order(tmp_path: Path):
    """First declared = bottom layer; last declared = top. Chain of
    v_secov0 → v_secov1 should be visible in the filter graph."""
    p, _v1, _v2 = _section_project(tmp_path)
    a = tmp_path / "a.png"; a.write_bytes(b"")
    b = tmp_path / "b.png"; b.write_bytes(b"")
    p.sections[0].overlays.extend([
        SectionOverlay(id="ov1", kind="image", file=str(a)),
        SectionOverlay(id="ov2", kind="image", file=str(b)),
    ])
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    fc = cmd.filter_complex
    assert "v_secov0" in fc
    assert "v_secov1" in fc
    # Second overlay composites onto the first (chain)
    assert "[v_secov0]" in fc


def test_audio_overlay_registers_input_and_mixes(tmp_path: Path):
    """A section-level audio overlay becomes an additional audio input,
    prepped (resample + format + delay + gain) and amix'd into the
    main audio at mix_pct share."""
    p, _v1, _v2 = _section_project(tmp_path)
    mp3 = tmp_path / "bed.mp3"
    mp3.write_bytes(b"")
    p.sections[1].overlays.append(SectionOverlay(
        id="ov1", kind="audio", file=str(mp3), mix_pct=50,
    ))
    layout = lay_out(p, probe=lambda _p: 2000)
    cmd = build_ffmpeg_command(p, layout)
    assert any(inp.path == str(mp3) for inp in cmd.inputs)
    fc = cmd.filter_complex
    # Resample + stereo format
    assert "aresample=48000" in fc
    assert "aformat=channel_layouts=stereo" in fc
    # 50% mix = overlay volume 0.5, main duck volume 0.5 during the window
    assert "volume=0.5" in fc
    # amix with 2 inputs, explicit normalize off, main-length-wins
    assert "amix=inputs=2:normalize=0:duration=first" in fc


def test_audio_overlay_respects_section_start_offset(tmp_path: Path):
    """Section 2 starts at 2s (section 1 was 2s). An overlay on sec 2
    with start_s=0.5 should delay by 2500 ms in the filter graph."""
    p, _v1, _v2 = _section_project(tmp_path)
    mp3 = tmp_path / "bed.mp3"
    mp3.write_bytes(b"")
    p.sections[1].overlays.append(SectionOverlay(
        id="ov1", kind="audio", file=str(mp3),
        start_s=0.5, mix_pct=100,
    ))
    layout = lay_out(p, probe=lambda _p: 2000)
    cmd = build_ffmpeg_command(p, layout)
    # Section 2 absolute start = 2s; + overlay start_s 0.5 = 2.5s ≈ 2500ms
    assert "adelay=2500|2500" in cmd.filter_complex


def test_audio_overlay_100_pct_mutes_main(tmp_path: Path):
    """mix_pct=100 means 'overlay only'; the main audio gets volume=0
    within the overlay window."""
    p, _v1, _v2 = _section_project(tmp_path)
    mp3 = tmp_path / "bed.mp3"
    mp3.write_bytes(b"")
    p.sections[0].overlays.append(SectionOverlay(
        id="ov1", kind="audio", file=str(mp3), mix_pct=100,
    ))
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    fc = cmd.filter_complex
    # Main duck volume = 1 - 1.0 = 0
    assert "volume=0:enable=" in fc


def test_audio_overlay_0_pct_does_not_duck_main(tmp_path: Path):
    """mix_pct=0 leaves the main at full; overlay is effectively
    silent. The ducking filter is skipped to keep the graph minimal."""
    p, _v1, _v2 = _section_project(tmp_path)
    mp3 = tmp_path / "bed.mp3"
    mp3.write_bytes(b"")
    p.sections[0].overlays.append(SectionOverlay(
        id="ov1", kind="audio", file=str(mp3), mix_pct=0,
    ))
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    assert "a_main_dim" not in cmd.filter_complex


def test_audio_overlay_fades_are_on_overlay_timeline(tmp_path: Path):
    """Fade-in st should equal the absolute start time; fade-out should
    start fade_out_s seconds before the absolute end."""
    p, _v1, _v2 = _section_project(tmp_path)
    mp3 = tmp_path / "bed.mp3"
    mp3.write_bytes(b"")
    # Section 1 covers 0-2s; overlay starts at 0s, ends at 2s (full section).
    p.sections[0].overlays.append(SectionOverlay(
        id="ov1", kind="audio", file=str(mp3),
        fade_in_s=0.5, fade_out_s=0.5, mix_pct=50,
    ))
    layout = lay_out(p, probe=lambda _p: 2000)
    cmd = build_ffmpeg_command(p, layout)
    fc = cmd.filter_complex
    # fade in starts at absolute 0s for 0.5s
    assert "afade=t=in:st=0:d=0.5" in fc
    # fade out starts at absolute 1.5s (abs_end - fade_out)
    assert "afade=t=out:st=1.5:d=0.5" in fc


def test_audio_overlay_ignored_for_image_kind(tmp_path: Path):
    """An image-only overlay shouldn't touch the audio filter chain."""
    p, _v1, _v2 = _section_project(tmp_path)
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"")
    p.sections[0].overlays.append(SectionOverlay(
        id="ov1", kind="image", file=str(logo),
    ))
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    assert "a_secov" not in cmd.filter_complex
    assert "a_mixed" not in cmd.filter_complex


def test_audio_overlay_multiple_chain(tmp_path: Path):
    """Two audio overlays on one section produce a chain of amix
    outputs (a_mixed0 → a_mixed1 → ...), each layer stacking."""
    p, _v1, _v2 = _section_project(tmp_path)
    a = tmp_path / "a.mp3"; a.write_bytes(b"")
    b = tmp_path / "b.mp3"; b.write_bytes(b"")
    p.sections[0].overlays.extend([
        SectionOverlay(id="ov1", kind="audio", file=str(a), mix_pct=30),
        SectionOverlay(id="ov2", kind="audio", file=str(b), mix_pct=40),
    ])
    layout = lay_out(p, probe=lambda _p: 2000)
    cmd = build_ffmpeg_command(p, layout)
    fc = cmd.filter_complex
    assert "a_secov0" in fc
    assert "a_secov1" in fc
    assert "a_mixed0" in fc
    assert "a_mixed1" in fc


def test_section_overlay_scale_emits_scale_filter(tmp_path: Path):
    """scale_pct != 100 should inject `format=rgba,scale=iw*r:ih*r`
    before the overlay composite. Forcing format=rgba PRE-scale stops
    ffmpeg from picking a YUV intermediate that turns transparent
    PNG backgrounds opaque."""
    p, _v1, _v2 = _section_project(tmp_path)
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"")
    p.sections[0].overlays.append(SectionOverlay(
        id="ov1", kind="image", file=str(logo),
        scale_pct=50, position="bl",
    ))
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    fc = cmd.filter_complex
    # Ratio 0.5 renders as "scale=iw*0.5:ih*0.5" in the graph
    assert "scale=iw*0.5:ih*0.5" in fc
    # format=rgba must come before the scale (alpha preservation)
    assert "format=rgba,scale=iw*0.5:ih*0.5" in fc
    # Scaled label feeds into the overlay, not the raw input
    assert "v_secov0_scaled" in fc


def test_section_overlay_scale_100_skips_scale_filter(tmp_path: Path):
    """Native size = no extra scale node (keeps the graph minimal)."""
    p, _v1, _v2 = _section_project(tmp_path)
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"")
    p.sections[0].overlays.append(SectionOverlay(
        id="ov1", kind="image", file=str(logo), scale_pct=100,
    ))
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    assert "v_secov0_scaled" not in cmd.filter_complex


def test_section_overlay_applies_before_bug(tmp_path: Path):
    """Bug overlay must composite ON TOP of section overlays (branding
    stays visible). Section overlay's output label feeds into the bug
    overlay, not the other way around."""
    p, _v1, _v2 = _section_project(tmp_path)
    logo = tmp_path / "logo.png"; logo.write_bytes(b"")
    bug = tmp_path / "bug.png"; bug.write_bytes(b"")
    p.sections[0].overlays.append(SectionOverlay(
        id="ov1", kind="image", file=str(logo),
    ))
    p.output.bug = BugOverlay(file=str(bug), corner="br")
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    assert cmd.map_video == "[v_bugged]"
    # The bug stage references the last section-overlay label as its input
    assert "[v_secov0][bug_rgba]" in cmd.filter_complex


# ── Closing fade-to-black ─────────────────────────────────────────────
def test_closing_fade_to_black_applies_to_video_and_audio(tmp_path: Path):
    """When output.closing_joiner is fade_to_black, the engine appends
    fade=t=out and afade=t=out filters to the final video and audio
    streams. Start time = total_duration - duration_s; end time = total.
    """
    p, _v1, _v2 = _section_project(tmp_path)
    p.output.closing_joiner = Joiner(
        id="join-close", joiner_type="fade_to_black",
        params={"duration_s": 1.5},
    )
    # Each section is 2s long; total = 4s. Fade should start at 2.5s.
    layout = lay_out(p, probe=lambda _p: 2000)
    cmd = build_ffmpeg_command(p, layout)
    fc = cmd.filter_complex
    assert "fade=t=out:st=2.5:d=1.5" in fc
    assert "afade=t=out:st=2.5:d=1.5" in fc
    assert cmd.map_video == "[v_close]"
    assert cmd.map_audio == "[a_close]"


def test_closing_fade_none_emits_no_fade_filter(tmp_path: Path):
    """Default closing_joiner ("none") means no fade at the tail."""
    p, _v1, _v2 = _section_project(tmp_path)
    layout = lay_out(p, probe=lambda _p: 2000)
    cmd = build_ffmpeg_command(p, layout)
    assert "fade=t=out" not in cmd.filter_complex
    assert "afade=t=out" not in cmd.filter_complex
    assert "v_close" not in cmd.filter_complex
    assert "a_close" not in cmd.filter_complex


def test_closing_fade_runs_after_bug_so_bug_fades_too(tmp_path: Path):
    """Closing fade should apply AFTER the bug overlay so the bug fades
    to black with the rest of the frame."""
    bug = tmp_path / "bug.png"
    bug.write_bytes(b"")
    p, _v1, _v2 = _section_project(tmp_path)
    p.output.bug = BugOverlay(file=str(bug), corner="br")
    p.output.closing_joiner = Joiner(
        id="join-close", joiner_type="fade_to_black",
        params={"duration_s": 1.0},
    )
    layout = lay_out(p, probe=lambda _p: 2000)
    cmd = build_ffmpeg_command(p, layout)
    fc = cmd.filter_complex
    # v_bugged is produced by the bug stage; the closing fade consumes
    # it to produce v_close.
    assert "[v_bugged]fade=t=out" in fc


def test_closing_fade_roundtrips_through_json(tmp_path: Path):
    """Output.closing_joiner round-trips cleanly through to_dict/from_dict."""
    o = Output(
        folder=str(tmp_path),
        closing_joiner=Joiner(
            id="join-close", joiner_type="fade_to_black",
            params={"duration_s": 2.5},
        ),
    )
    d = o.to_dict()
    assert "closing_joiner" in d
    o2 = Output.from_dict(d)
    assert o2.closing_joiner.joiner_type == "fade_to_black"
    assert o2.closing_joiner.params["duration_s"] == 2.5
