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


def test_output_path_carries_the_rendered_size(tmp_path: Path):
    """A compilation gets rendered more than once -- 1080p for the phone, 4k
    for the TV. Without the size in the name the second render silently
    replaces the first."""
    v = _mp4(tmp_path, "a")
    p = _project(tmp_path, Segment(id="s1", video=str(v)))
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    assert cmd.output_path == str(tmp_path / "out" / "combined.1080p30.mp4")


def test_output_path_names_the_size_actually_encoded(tmp_path: Path):
    """Not the setting. `resolution='source'` must not produce a file called
    `combined.source.mp4` -- the tag reports what came out."""
    v = _mp4(tmp_path, "a")
    p = _project(tmp_path, Segment(id="s1", video=str(v)))
    p.output.resolution = "source"
    p.output.frame_rate = "source"
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout,
                               resolution_override=(3840, 2160),
                               frame_rate_override=60)
    assert cmd.output_path == str(tmp_path / "out" / "combined.4k60.mp4")


def test_an_explicit_output_path_is_left_exactly_as_given(tmp_path: Path):
    """The caller named the file; adding to it would be a surprise."""
    v = _mp4(tmp_path, "a")
    p = _project(tmp_path, Segment(id="s1", video=str(v)))
    layout = lay_out(p, probe=lambda _p: 1000)
    want = str(tmp_path / "chosen.mp4")
    cmd = build_ffmpeg_command(p, layout, output_path=want)
    assert cmd.output_path == want


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


# ── GPU / hardware encoder selection ──────────────────────────────────
def test_encoder_none_defaults_to_libx264(tmp_path: Path):
    """No encoder arg → the deterministic CPU path (what the pure builder and
    every existing test assume)."""
    v = _mp4(tmp_path, "a")
    p = _project(tmp_path, Segment(id="s1", video=str(v)))
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    assert "libx264" in cmd.output_args
    assert "h264_nvenc" not in cmd.output_args


def test_encoder_nvenc_emits_h264_nvenc_with_cq(tmp_path: Path):
    """encoder='nvenc' → NVIDIA hardware H.264, CRF mapped onto NVENC -cq."""
    v = _mp4(tmp_path, "a")
    p = _project(tmp_path, Segment(id="s1", video=str(v)))
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout, encoder="nvenc")
    assert "h264_nvenc" in cmd.output_args
    assert "libx264" not in cmd.output_args
    cq_idx = cmd.output_args.index("-cq")
    assert cmd.output_args[cq_idx + 1] == "23"  # medium → 23, mirrored to -cq
    assert "-crf" not in cmd.output_args


def test_encoder_env_override_forces_cpu(tmp_path, monkeypatch):
    """FORGEASSEMBLER_ENCODER=x264 pins the CPU encoder regardless of hardware."""
    from forgeassembler_core.concat_video import resolve_video_encoder
    monkeypatch.setenv("FORGEASSEMBLER_ENCODER", "x264")
    assert resolve_video_encoder(ffmpeg_exe="ffmpeg") == "libx264"


def test_encoder_env_override_forces_named_hw(tmp_path, monkeypatch):
    """An explicit hardware name is trusted without probing."""
    from forgeassembler_core.concat_video import resolve_video_encoder
    monkeypatch.setenv("FORGEASSEMBLER_ENCODER", "amf")
    assert resolve_video_encoder(ffmpeg_exe="ffmpeg") == "amf"


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
    assert "overlay=x=W*0.05:y=H-h-H*0.05" in cmd.filter_complex


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


def test_section_image_overlay_input_covers_its_enable_window(
    tmp_path: Path,
):
    """The image stream must carry the ABSOLUTE timestamps its enable
    window and its alpha fades are written in — but it must not be
    GENERATED from t=0 to get them.

    Two bugs live at this line. Capping the read at `effective_dur` alone
    made the stream end long before `enable` opened, because its timestamps
    started at zero and the window is measured from the start of the output.
    Fixing that with `-t abs_end_s` made a credits logo ending at 59 minutes
    a 4K still looped for 59 minutes — measured at 4.4 GB of the 14.2 GB a
    real 4K forge needed, for an overlay enabled for five seconds of it.

    `-itsoffset` gives both, so this asserts the WINDOW rather than either
    spelling of it.

    Section 1 = 0..2s, Section 2 = 2..4s. Overlay on sec 2 with
    start_s=0.5, duration_s=1.0 → visible 2.5..3.5 on the output.
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
    args = matches[0].pre_args
    offset = float(args[args.index("-itsoffset") + 1])
    read = float(args[args.index("-t") + 1])

    assert offset == pytest.approx(2.5), (
        f"the stream must LAND at abs_start_s=2.5; got -itsoffset {offset}"
    )
    assert read == pytest.approx(1.0), (
        f"only the window itself should be read; got -t {read}"
    )
    # The invariant both spellings exist to satisfy.
    assert offset + read == pytest.approx(3.5), (
        "the image must still be alive when the enable window closes"
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
    # Bottom-right places overlay near (W-w, H-h) with 5% breathing room
    assert "overlay=x=W-w-W*0.05:y=H-h-H*0.05" in cmd.filter_complex


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


# ── Text overlays ─────────────────────────────────────────────────────
def _make_font_file(tmp_path: Path) -> Path:
    """Drop a zero-byte .ttf in tmp so tests can point the engine at a
    file that 'exists'. The engine only cares about the path string; it
    never parses the font itself."""
    font = tmp_path / "TestFont.ttf"
    font.write_bytes(b"")
    return font


def test_text_overlay_emits_drawtext(tmp_path: Path, monkeypatch):
    """A section text overlay should render as a drawtext filter with
    escaped text, the resolved fontfile path, and an absolute-time
    enable window."""
    p, _v1, _v2 = _section_project(tmp_path)
    font = _make_font_file(tmp_path)

    # Stub the font resolver so the test doesn't depend on what's
    # installed on the host.
    from forgeassembler_core import fonts as fonts_mod
    monkeypatch.setattr(
        fonts_mod, "resolve_font_path",
        lambda stem: str(font) if stem == "TestFont" else None,
    )

    p.sections[1].overlays.append(SectionOverlay(
        id="ov-text", kind="text", file="",
        start_s=0.5, duration_s=1.0,
        position="center",
        text="Hello world",
        text_color="#ff0000",
        font_size=64,
        font_family="TestFont",
    ))
    layout = lay_out(p, probe=lambda _p: 2000)
    cmd = build_ffmpeg_command(p, layout)
    fc = cmd.filter_complex
    # Section 2 starts at 2s, overlay start_s=0.5 → abs 2.5..3.5
    assert "drawtext=" in fc
    assert "text='Hello world'" in fc
    assert "fontsize=64" in fc
    assert "fontcolor=#ff0000" in fc
    assert "enable='between(t,2.5,3.5)'" in fc
    # fontfile path should be present with forward slashes + escaped colon
    assert font.name in fc


def test_text_overlay_escapes_newlines(tmp_path: Path, monkeypatch):
    """Literal newline bytes in the text would terminate ffmpeg's
    filter_complex chain, breaking the whole graph. They must be
    converted to the two-char `\\n` escape that drawtext renders as
    a line break."""
    p, _v1, _v2 = _section_project(tmp_path)
    font = _make_font_file(tmp_path)
    from forgeassembler_core import fonts as fonts_mod
    monkeypatch.setattr(
        fonts_mod, "resolve_font_path", lambda _stem: str(font),
    )
    p.sections[0].overlays.append(SectionOverlay(
        id="ov-text", kind="text", file="",
        text="line one\nline two",
        font_family="TestFont",
    ))
    layout = lay_out(p, probe=lambda _p: 2000)
    cmd = build_ffmpeg_command(p, layout)
    fc = cmd.filter_complex
    # No literal newlines inside the drawtext text=... value. The
    # easiest check: the drawtext node must stay on a single filter
    # chain line. Grab everything between drawtext and the next ;
    # and verify no \n bytes.
    import re
    m = re.search(r"drawtext=[^;]+", fc)
    assert m, "expected a drawtext filter in the graph"
    assert "\n" not in m.group(0)
    # And the two-char escape should be present.
    assert "line one\\nline two" in fc


def test_text_overlay_escapes_special_chars(tmp_path: Path, monkeypatch):
    """Colons, backslashes and percent signs must be escaped with a
    preceding backslash. Apostrophes use the shell-style
    close-escape-reopen sequence `'\\''` so filter_complex doesn't
    terminate the single-quoted region early."""
    p, _v1, _v2 = _section_project(tmp_path)
    font = _make_font_file(tmp_path)
    from forgeassembler_core import fonts as fonts_mod
    monkeypatch.setattr(
        fonts_mod, "resolve_font_path", lambda _stem: str(font),
    )
    p.sections[0].overlays.append(SectionOverlay(
        id="ov-text", kind="text", file="",
        text="100%: it's 'great' \\ on track",
        font_family="TestFont",
    ))
    layout = lay_out(p, probe=lambda _p: 2000)
    cmd = build_ffmpeg_command(p, layout)
    fc = cmd.filter_complex
    # Percent + colon get backslash-escaped.
    assert "100\\%" in fc
    # Apostrophes use close-escape-open concat, NOT \' (which would
    # terminate the single-quoted region).
    assert "\\'" not in fc.replace("'\\''", "")  # no bare \' anywhere
    assert "it'\\''s" in fc
    assert "'\\''great'\\''" in fc
    # Double-escaped backslash (one in source → two in escaped)
    assert "\\\\" in fc


def test_text_overlay_uses_textfile_when_provided(tmp_path: Path, monkeypatch):
    """Runtime path: when `text_files` maps the overlay id to a
    tempfile path, drawtext uses `textfile='<path>':expansion=none`
    instead of inline `text=...`. This sidesteps all the fragile
    inline-escape traps (newlines, apostrophes, colons) because
    ffmpeg reads literal bytes from disk."""
    p, _v1, _v2 = _section_project(tmp_path)
    font = _make_font_file(tmp_path)
    from forgeassembler_core import fonts as fonts_mod
    monkeypatch.setattr(
        fonts_mod, "resolve_font_path", lambda _stem: str(font),
    )
    text_path = tmp_path / "text_ov-text.txt"
    text_path.write_text("line one\nline two\nlet's test", encoding="utf-8")
    p.sections[0].overlays.append(SectionOverlay(
        id="ov-text", kind="text", file="",
        text="line one\nline two\nlet's test",
        font_family="TestFont",
    ))
    layout = lay_out(p, probe=lambda _p: 2000)
    cmd = build_ffmpeg_command(
        p, layout, text_files={"ov-text": str(text_path)},
    )
    fc = cmd.filter_complex
    # textfile= present, inline text= absent, expansion=none set
    assert "textfile=" in fc
    assert ":text=" not in fc  # inline form should not appear
    assert "expansion=none" in fc
    # The path goes through the same colon-escape as fontfile.
    escaped = str(text_path).replace("\\", "/").replace(":", "\\:")
    assert escaped in fc


def test_text_overlay_url_with_colons(tmp_path: Path, monkeypatch):
    """A URL like 'http://funscriptforge.com' must escape every colon
    so drawtext doesn't mistake 'http' as an option key. Slashes are
    literal and need no escape."""
    p, _v1, _v2 = _section_project(tmp_path)
    font = _make_font_file(tmp_path)
    from forgeassembler_core import fonts as fonts_mod
    monkeypatch.setattr(
        fonts_mod, "resolve_font_path", lambda _stem: str(font),
    )
    p.sections[0].overlays.append(SectionOverlay(
        id="ov-text", kind="text", file="",
        text="http://funscriptforge.com",
        font_family="TestFont",
    ))
    layout = lay_out(p, probe=lambda _p: 2000)
    cmd = build_ffmpeg_command(p, layout)
    fc = cmd.filter_complex
    # Colon escaped, slashes left alone.
    assert "http\\://funscriptforge.com" in fc


def test_text_overlay_skipped_when_no_font_resolves(
    tmp_path: Path, monkeypatch,
):
    """When the font stem doesn't resolve and the machine has no fonts
    at all, the overlay is silently skipped (no filter emitted). With
    fonts available, it falls back to the first one."""
    p, _v1, _v2 = _section_project(tmp_path)
    from forgeassembler_core import fonts as fonts_mod
    monkeypatch.setattr(fonts_mod, "resolve_font_path", lambda _stem: None)
    monkeypatch.setattr(fonts_mod, "list_fonts", lambda: [])

    p.sections[0].overlays.append(SectionOverlay(
        id="ov-text", kind="text", file="",
        text="won't render", font_family="NotInstalled",
    ))
    layout = lay_out(p, probe=lambda _p: 2000)
    cmd = build_ffmpeg_command(p, layout)
    assert "drawtext=" not in cmd.filter_complex


def test_text_overlay_falls_back_to_first_font(
    tmp_path: Path, monkeypatch,
):
    """When the stem doesn't resolve but other fonts are installed,
    the engine uses the first available one so text still renders."""
    p, _v1, _v2 = _section_project(tmp_path)
    font = _make_font_file(tmp_path)
    from forgeassembler_core import fonts as fonts_mod
    monkeypatch.setattr(fonts_mod, "resolve_font_path", lambda _stem: None)
    monkeypatch.setattr(
        fonts_mod, "list_fonts", lambda: [("Fallback", str(font))],
    )
    p.sections[0].overlays.append(SectionOverlay(
        id="ov-text", kind="text", file="",
        text="hi", font_family="Missing",
    ))
    layout = lay_out(p, probe=lambda _p: 2000)
    cmd = build_ffmpeg_command(p, layout)
    assert "drawtext=" in cmd.filter_complex
    assert font.name in cmd.filter_complex


def test_text_overlay_roundtrips_json(tmp_path: Path):
    """A text SectionOverlay survives to_dict/from_dict cleanly."""
    ov = SectionOverlay(
        id="ov-text", kind="text", file="",
        text="Round trip", text_color="#00ff00",
        font_size=48, font_family="Arial",
        start_s=1.0, duration_s=2.5, fade_in_s=0.3, fade_out_s=0.7,
        position="tc", opacity=0.8,
    )
    d = ov.to_dict()
    assert d["kind"] == "text"
    assert "file" not in d or d.get("file") == ""
    ov2 = SectionOverlay.from_dict(d)
    assert ov2.text == "Round trip"
    assert ov2.text_color == "#00ff00"
    assert ov2.font_size == 48
    assert ov2.font_family == "Arial"
    assert ov2.position == "tc"


# ── Title card joiner renders into the graph ──────────────────────────

def _two_scene_project(joiner):
    from forgeassembler_core.project import Project

    return Project.from_dict({
        "version": 1,
        "output": {"folder": ".", "basename": "t", "resolution": "1080p"},
        "sections": [
            {"id": "s1", "title": "A",
             "leading_joiner": {"id": "j1", "joiner_type": "none", "params": {}},
             "segments": [{"id": "g1", "video": "a.mp4"}]},
            {"id": "s2", "title": "B", "leading_joiner": joiner,
             "segments": [{"id": "g2", "video": "b.mp4"}]},
        ]})


def _graph(joiner, **kwargs):
    from forgeassembler_core.concat_video import build_ffmpeg_command
    from forgeassembler_core.layout import lay_out

    project = _two_scene_project(joiner)
    layout = lay_out(project, probe=lambda p: 10000)
    cmd = build_ffmpeg_command(project, layout, frame_rate_override=30,
                               **kwargs)
    return " ".join(cmd.to_argv("ffmpeg"))


TITLE_JOINER = {
    "id": "j2", "joiner_type": "title_card",
    "params": {"title": "Part Two", "duration_s": 3.0, "fade_s": 1.0},
}


def test_title_card_composites_its_card_on_its_own_bridge():
    # The bridge is the theme's background -- #0e1117 for the default
    # dark theme, not black -- because the fades either side land on it
    # and a card that disagreed with its own bridge would flash.
    g = _graph(TITLE_JOINER, title_cards={"j2": "card.png"})
    assert "color=c=0x0e1117:s=1920x1080:d=3" in g
    assert "card.png" in g
    assert "overlay=" in g
    # The card is a picture now. Nothing draws words into the graph.
    assert "drawtext" not in g


def test_a_card_that_did_not_render_still_forges_as_a_fade():
    # A card with nothing to say does not get a PNG, and losing the
    # whole encode over it would be a poor trade.
    g = _graph(TITLE_JOINER)
    assert "color=c=0x0e1117:s=1920x1080:d=3" in g
    assert "overlay=" not in g


def test_title_card_is_visible_for_the_whole_card():
    # Relative to the bridge, which starts at 0 -- not absolute time on
    # the concatenated timeline, the way section overlays are placed.
    assert "enable='between(t,0,3)'" in _graph(
        TITLE_JOINER, title_cards={"j2": "card.png"})


def test_title_card_fades_its_neighbours_like_a_fade_does():
    # The regression this guards: the fade lookup tested
    # `joiner_type == "fade_to_black"`, so a title card hard-cut into
    # its own bridge no matter what its params said.
    g = _graph(TITLE_JOINER)
    assert "fade=t=out:st=9:d=1" in g, "previous scene must fade out"
    assert "fade=t=in:st=0:d=1" in g, "next scene must fade in"


def test_a_scene_fades_to_the_colour_it_is_fading_INTO():
    # ffmpeg's `fade` goes to BLACK unless told otherwise, so a card on
    # any other colour dipped the scene to black and then cut to the
    # hold. Measured on a real encode before the fix: a #1a0e1e card
    # with a 0.5s fade read (0, 0, 0) at the corner mid-fade.
    j = {**TITLE_JOINER}
    j["params"] = {**j["params"], "theme": "brand"}
    g = _graph(j, title_cards={"j2": "card.png"})
    assert "color=0x1a0e1e" in g, "the fade must land on the card's colour"


def test_a_black_fade_is_still_spelled_the_old_way():
    # Saying `color=0x000000` would change the filtergraph of every
    # project that was already forging, for no visible difference.
    g = _graph({
        "id": "j2", "joiner_type": "fade_to_black",
        "params": {"duration_s": 3.0, "fade_s": 1.0},
    })
    assert "fade=t=out:st=9:d=1" in g
    assert "color=0x" not in g


def test_a_cut_still_produces_no_bridge():
    g = _graph({"id": "j2", "joiner_type": "none", "params": {}})
    assert "color=c=" not in g
    assert "overlay=" not in g


# ── Title-card frame backgrounds ──────────────────────────────────────
# "The last frame of the previous scene" is very often the frame with
# nothing on it, because scenes fade out. These pin the rejection rule.

def _paint_png(tmp_path, name, make):
    from PIL import Image

    img = Image.new("RGB", (64, 36))
    img.putdata([make(x, y) for y in range(36) for x in range(64)])
    p = tmp_path / name
    img.save(p)
    return str(p)


def test_a_black_frame_is_blank(tmp_path):
    from forgeassembler_core.concat_video import _frame_is_blank

    assert _frame_is_blank(_paint_png(tmp_path, "black.png", lambda x, y: (0, 0, 0)))


def test_a_nearly_black_fade_frame_is_blank(tmp_path):
    from forgeassembler_core.concat_video import _frame_is_blank

    assert _frame_is_blank(_paint_png(tmp_path, "fade.png", lambda x, y: (4, 4, 5)))


def test_a_white_flash_is_blank_too(tmp_path):
    # Bright, but no more interesting than black. Brightness alone would
    # happily pick this.
    from forgeassembler_core.concat_video import _frame_is_blank

    assert _frame_is_blank(_paint_png(tmp_path, "white.png", lambda x, y: (255, 255, 255)))


def test_a_flat_colour_card_is_blank(tmp_path):
    from forgeassembler_core.concat_video import _frame_is_blank

    assert _frame_is_blank(_paint_png(tmp_path, "flat.png", lambda x, y: (30, 90, 160)))


def test_a_frame_with_a_picture_on_it_is_not_blank(tmp_path):
    from forgeassembler_core.concat_video import _frame_is_blank

    path = _paint_png(tmp_path, "real.png",
                lambda x, y: ((x * 4) % 256, (y * 7) % 256, (x + y) % 256))
    assert not _frame_is_blank(path)


def test_a_dark_but_readable_frame_is_not_blank(tmp_path):
    # A night scene must survive: it is dim, but there is something there.
    from forgeassembler_core.concat_video import _frame_is_blank

    path = _paint_png(tmp_path, "night.png",
                lambda x, y: (8 + (x % 40), 6 + (y % 30), 10 + ((x + y) % 35)))
    assert not _frame_is_blank(path)


def test_an_unreadable_file_counts_as_blank(tmp_path):
    from forgeassembler_core.concat_video import _frame_is_blank

    bad = tmp_path / "not-an-image.png"
    bad.write_bytes(b"nope")
    assert _frame_is_blank(str(bad))
    assert _frame_is_blank(str(tmp_path / "does-not-exist.png"))


TITLE_ON_PREV_FRAME = {
    "id": "j2", "joiner_type": "title_card",
    "params": {"text": "Part Two", "duration_s": 3.0, "fade_s": 1.0,
               "background": "previous_last_frame"},
}


def test_a_frame_backed_card_takes_a_looped_image_input():
    from forgeassembler_core.concat_video import build_ffmpeg_command
    from forgeassembler_core.layout import lay_out

    project = _two_scene_project(TITLE_ON_PREV_FRAME)
    layout = lay_out(project, probe=lambda p: 10000)
    cmd = build_ffmpeg_command(project, layout, frame_rate_override=30,
                               joiner_frames={"j2": "prev.png"})
    argv = cmd.to_argv("ffmpeg")
    graph = " ".join(argv)
    assert "prev.png" in argv
    # Normalised to the canvas like a segment, so a 4:3 source pillarboxes
    # rather than stretching.
    assert "force_original_aspect_ratio=decrease" in graph
    # Pushed back so the title stays readable.
    #
    # ⚠ romax, the OUTPUT white point. This asserted `rimax` — the INPUT
    # white point — which stretches the range UPWARD: measured with
    # ffmpeg, rimax=0.55 took mid-grey 128 to 233. The control called
    # "Darken background" was brightening the frame under white text.
    # romax=0.55 takes the same 128 to 70.
    assert "colorlevels=romax=0.75" in graph   # the 0.25 default dim
    assert "rimax" not in graph
    assert "color=c=0x0e1117" not in graph, "a frame-backed card has no bridge colour"


def test_a_card_falls_back_to_flat_colour_when_every_frame_was_blank():
    # The honest outcome for a scene that really is black at that end.
    from forgeassembler_core.concat_video import build_ffmpeg_command
    from forgeassembler_core.layout import lay_out

    project = _two_scene_project(TITLE_ON_PREV_FRAME)
    layout = lay_out(project, probe=lambda p: 10000)
    graph = " ".join(build_ffmpeg_command(
        project, layout, frame_rate_override=30, joiner_frames={}).to_argv("ffmpeg"))
    assert "color=c=0x0e1117" in graph
    assert "colorlevels" not in graph


def test_dim_never_blacks_the_frame_out_entirely():
    from forgeassembler_core.concat_video import build_ffmpeg_command
    from forgeassembler_core.layout import lay_out

    j = {**TITLE_ON_PREV_FRAME}
    j["params"] = {**j["params"], "background_dim": 1.0}
    project = _two_scene_project(j)
    layout = lay_out(project, probe=lambda p: 10000)
    graph = " ".join(build_ffmpeg_command(
        project, layout, frame_rate_override=30,
        joiner_frames={"j2": "prev.png"}).to_argv("ffmpeg"))
    assert "romax=0.1" in graph, "a fully dimmed card would look broken"
