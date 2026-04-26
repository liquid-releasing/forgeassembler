# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Tests for the per-channel haptic-estim audio concat (v0.0.4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from forgeassembler_core.concat_audio_estim import (
    AUDIO_ESTIM_CHANNELS,
    build_audio_estim_command,
    channel_files_for_layout,
    channel_has_any_audio,
)
from forgeassembler_core.detect import audio_estim_for_stem
from forgeassembler_core.layout import lay_out
from forgeassembler_core.project import (
    Joiner,
    Output,
    Project,
    Segment,
)


def _mp4(tmp: Path, name: str) -> Path:
    p = tmp / f"{name}.mp4"
    p.write_bytes(b"")
    return p


def _stim(tmp: Path, name: str, suffix: str) -> Path:
    """Create a placeholder estim audio file (`{name}.{suffix}`)."""
    p = tmp / f"{name}{suffix}"
    p.write_bytes(b"")  # contents irrelevant — engine builds an ffmpeg cmd
    return p


def _project(tmp: Path, *items, **overrides) -> Project:
    defaults = {"folder": str(tmp / "out"), "frame_rate": "30"}
    defaults.update(overrides)
    return Project(items=list(items), output=Output(**defaults))


# ── detection: subfolder scan parity ──────────────────────────────────
class TestAudioEstimDetection:
    def test_finds_in_immediate_folder(self, tmp_path: Path):
        _stim(tmp_path, "clip", ".stereostim.wav")
        found = audio_estim_for_stem(tmp_path, "clip")
        assert "stereostim.wav" in found

    def test_finds_in_audio_estim_subfolder(self, tmp_path: Path):
        sub = tmp_path / "audio_estim"
        sub.mkdir()
        (sub / "clip.legacy.wav").write_bytes(b"")
        found = audio_estim_for_stem(tmp_path, "clip")
        assert "legacy.wav" in found

    def test_finds_in_estim_subfolder(self, tmp_path: Path):
        """`estim/` subfolder also gets scanned (same as funscripts_for_stem)."""
        sub = tmp_path / "estim"
        sub.mkdir()
        (sub / "clip.prostate.stereostim.wav").write_bytes(b"")
        found = audio_estim_for_stem(tmp_path, "clip")
        assert "prostate.stereostim.wav" in found

    def test_immediate_folder_wins_over_subfolder(self, tmp_path: Path):
        """First hit wins: an immediate-folder file shadows the subfolder one."""
        _stim(tmp_path, "clip", ".stereostim.wav")
        sub = tmp_path / "audio_estim"
        sub.mkdir()
        (sub / "clip.stereostim.wav").write_bytes(b"")
        found = audio_estim_for_stem(tmp_path, "clip")
        assert found["stereostim.wav"].parent == tmp_path

    def test_no_files_returns_empty(self, tmp_path: Path):
        assert audio_estim_for_stem(tmp_path, "missing") == {}


# ── channel_files_for_layout / channel_has_any_audio ──────────────────
class TestChannelFilesForLayout:
    def test_segment_with_audio_returns_path(self, tmp_path: Path):
        v = _mp4(tmp_path, "a")
        _stim(tmp_path, "a", ".stereostim.wav")
        p = _project(tmp_path, Segment(id="s", video=str(v)))
        layout = lay_out(p, probe=lambda _p: 1000)
        files = channel_files_for_layout(p, layout, "stereostim.wav")
        assert len(files) == 1
        assert files[0] is not None
        assert files[0].name == "a.stereostim.wav"

    def test_segment_without_audio_returns_none(self, tmp_path: Path):
        v = _mp4(tmp_path, "a")  # no audio file alongside
        p = _project(tmp_path, Segment(id="s", video=str(v)))
        layout = lay_out(p, probe=lambda _p: 1000)
        files = channel_files_for_layout(p, layout, "stereostim.wav")
        assert files == [None]

    def test_joiner_contributes_none(self, tmp_path: Path):
        v1 = _mp4(tmp_path, "a")
        v2 = _mp4(tmp_path, "b")
        _stim(tmp_path, "a", ".stereostim.wav")
        _stim(tmp_path, "b", ".stereostim.wav")
        p = _project(
            tmp_path,
            Segment(id="s1", video=str(v1)),
            Joiner(id="j1", joiner_type="fade_to_black",
                   params={"duration_s": 1.0, "fade_s": 0.5}),
            Segment(id="s2", video=str(v2)),
        )
        layout = lay_out(p, probe=lambda _p: 1000)
        files = channel_files_for_layout(p, layout, "stereostim.wav")
        # 3 layout items: seg, joiner, seg
        assert len(files) == 3
        assert files[0] is not None
        assert files[1] is None  # joiner = silence
        assert files[2] is not None

    def test_still_segment_contributes_none(self, tmp_path: Path):
        png = tmp_path / "title.png"
        png.write_bytes(b"")
        # Even if a sibling file existed, still segments don't carry haptic audio.
        _stim(tmp_path, "title", ".stereostim.wav")
        p = _project(tmp_path, Segment(
            id="s", video=str(png), still_duration_s=2.0,
        ))
        layout = lay_out(p, probe=lambda _p: 1000)
        files = channel_files_for_layout(p, layout, "stereostim.wav")
        assert files == [None]


class TestChannelHasAnyAudio:
    def test_true_when_any_segment_has_audio(self, tmp_path: Path):
        v = _mp4(tmp_path, "a")
        _stim(tmp_path, "a", ".stereostim.wav")
        p = _project(tmp_path, Segment(id="s", video=str(v)))
        layout = lay_out(p, probe=lambda _p: 1000)
        assert channel_has_any_audio(p, layout, "stereostim.wav")

    def test_false_when_no_segment_has_audio(self, tmp_path: Path):
        v = _mp4(tmp_path, "a")
        p = _project(tmp_path, Segment(id="s", video=str(v)))
        layout = lay_out(p, probe=lambda _p: 1000)
        assert not channel_has_any_audio(p, layout, "stereostim.wav")

    def test_true_with_silence_fill_in_some_segments(self, tmp_path: Path):
        v1 = _mp4(tmp_path, "a")
        v2 = _mp4(tmp_path, "b")
        _stim(tmp_path, "a", ".stereostim.wav")  # b has no audio
        p = _project(
            tmp_path,
            Segment(id="s1", video=str(v1)),
            Segment(id="s2", video=str(v2)),
        )
        layout = lay_out(p, probe=lambda _p: 1000)
        assert channel_has_any_audio(p, layout, "stereostim.wav")


# ── build_audio_estim_command ─────────────────────────────────────────
class TestBuildAudioEstimCommand:
    def test_single_segment_with_audio(self, tmp_path: Path):
        v = _mp4(tmp_path, "a")
        a = _stim(tmp_path, "a", ".stereostim.wav")
        p = _project(tmp_path, Segment(id="s", video=str(v)))
        layout = lay_out(p, probe=lambda _p: 5000)
        out = str(tmp_path / "combined.stereostim.wav")
        cmd = build_audio_estim_command(p, layout, "stereostim.wav", out)
        # One real input, no silence
        assert any(inp.path == str(a) for inp in cmd.inputs)
        # No -ss/-t when untrimmed
        real_input = next(inp for inp in cmd.inputs if inp.path == str(a))
        assert real_input.pre_args == []
        # PCM output args
        assert "-c:a" in cmd.output_args
        assert cmd.output_args[cmd.output_args.index("-c:a") + 1] == "pcm_s16le"

    def test_trimmed_segment_emits_ss_and_t(self, tmp_path: Path):
        v = _mp4(tmp_path, "a")
        a = _stim(tmp_path, "a", ".stereostim.wav")
        p = _project(tmp_path, Segment(
            id="s", video=str(v),
            trim_start="00:00:10.000", trim_end="00:00:30.000",
        ))
        layout = lay_out(p, probe=lambda _p: 60_000)
        out = str(tmp_path / "out.wav")
        cmd = build_audio_estim_command(p, layout, "stereostim.wav", out)
        real_input = next(inp for inp in cmd.inputs if inp.path == str(a))
        # -ss 10 -t 20 — same window as the video pipeline
        assert real_input.pre_args == ["-ss", "10", "-t", "20"]

    def test_missing_audio_becomes_anullsrc(self, tmp_path: Path):
        v = _mp4(tmp_path, "a")  # no audio file alongside
        p = _project(tmp_path, Segment(id="s", video=str(v)))
        layout = lay_out(p, probe=lambda _p: 5000)
        out = str(tmp_path / "out.wav")
        cmd = build_audio_estim_command(p, layout, "stereostim.wav", out)
        # No real input
        assert cmd.inputs == []
        # filter_complex contains anullsrc
        assert "anullsrc" in cmd.filter_complex

    def test_joiner_inserts_silence_for_its_duration(self, tmp_path: Path):
        v1 = _mp4(tmp_path, "a")
        v2 = _mp4(tmp_path, "b")
        _stim(tmp_path, "a", ".stereostim.wav")
        _stim(tmp_path, "b", ".stereostim.wav")
        p = _project(
            tmp_path,
            Segment(id="s1", video=str(v1)),
            Joiner(id="j1", joiner_type="fade_to_black",
                   params={"duration_s": 2.0, "fade_s": 0.5}),
            Segment(id="s2", video=str(v2)),
        )
        layout = lay_out(p, probe=lambda _p: 1000)
        out = str(tmp_path / "out.wav")
        cmd = build_audio_estim_command(p, layout, "stereostim.wav", out)
        # Joiner becomes anullsrc with d=2 (the joiner's own duration)
        assert "anullsrc=d=2" in cmd.filter_complex

    def test_concat_filter_links_n_streams(self, tmp_path: Path):
        v1 = _mp4(tmp_path, "a")
        v2 = _mp4(tmp_path, "b")
        _stim(tmp_path, "a", ".stereostim.wav")
        _stim(tmp_path, "b", ".stereostim.wav")
        p = _project(
            tmp_path,
            Segment(id="s1", video=str(v1)),
            Segment(id="s2", video=str(v2)),
        )
        layout = lay_out(p, probe=lambda _p: 1000)
        out = str(tmp_path / "out.wav")
        cmd = build_audio_estim_command(p, layout, "stereostim.wav", out)
        # concat=n=2:v=0:a=1
        assert "concat=n=2:v=0:a=1" in cmd.filter_complex

    def test_single_item_skips_concat_filter(self, tmp_path: Path):
        """One layout item doesn't need a concat filter at all."""
        v = _mp4(tmp_path, "a")
        _stim(tmp_path, "a", ".stereostim.wav")
        p = _project(tmp_path, Segment(id="s", video=str(v)))
        layout = lay_out(p, probe=lambda _p: 1000)
        out = str(tmp_path / "out.wav")
        cmd = build_audio_estim_command(p, layout, "stereostim.wav", out)
        # No concat= because only one segment
        assert "concat=" not in cmd.filter_complex


# ── output args + map ──────────────────────────────────────────────────
class TestAudioEstimOutputs:
    def test_targets_48k_stereo(self, tmp_path: Path):
        v = _mp4(tmp_path, "a")
        _stim(tmp_path, "a", ".stereostim.wav")
        p = _project(tmp_path, Segment(id="s", video=str(v)))
        layout = lay_out(p, probe=lambda _p: 1000)
        out = str(tmp_path / "out.wav")
        cmd = build_audio_estim_command(p, layout, "stereostim.wav", out)
        # 48000 Hz, 2-channel stereo
        assert "-ar" in cmd.output_args
        assert cmd.output_args[cmd.output_args.index("-ar") + 1] == "48000"
        assert "-ac" in cmd.output_args
        assert cmd.output_args[cmd.output_args.index("-ac") + 1] == "2"

    def test_no_video_mapping(self, tmp_path: Path):
        v = _mp4(tmp_path, "a")
        _stim(tmp_path, "a", ".stereostim.wav")
        p = _project(tmp_path, Segment(id="s", video=str(v)))
        layout = lay_out(p, probe=lambda _p: 1000)
        out = str(tmp_path / "out.wav")
        cmd = build_audio_estim_command(p, layout, "stereostim.wav", out)
        assert cmd.map_video is None
        assert cmd.map_audio is not None


# ── empty-layout safety ───────────────────────────────────────────────
class TestEmptyLayout:
    def test_raises_on_empty_layout(self, tmp_path: Path):
        p = _project(tmp_path)  # no items
        layout = lay_out(p, probe=lambda _p: 0)
        with pytest.raises(ValueError):
            build_audio_estim_command(
                p, layout, "stereostim.wav", str(tmp_path / "out.wav"),
            )


# ── channel suffix mapping ─────────────────────────────────────────────
class TestChannelSuffixes:
    def test_back_compat_per_channel_wav_constants(self):
        """`AUDIO_ESTIM_CHANNELS` is kept (pinned to the per-channel WAV
        split) for back-compat with v0.0.4 callers / tests. New code
        uses `discover_channels_in_layout()` to enumerate dynamically."""
        keys = [k for k, _ in AUDIO_ESTIM_CHANNELS]
        suffixes = [s for _, s in AUDIO_ESTIM_CHANNELS]
        assert keys == [
            "stereostim.wav",
            "legacy.wav",
            "prostate.stereostim.wav",
        ]
        assert suffixes == [
            ".stereostim.wav",
            ".legacy.wav",
            ".prostate.stereostim.wav",
        ]


# ── MP3 / generic detection (v0.0.5 fix) ──────────────────────────────
class TestMp3Detection:
    def test_segment_with_mp3_only_resolves(self, tmp_path: Path):
        """The real-world case: only `{stem}.mp3` exists alongside the
        video. v0.0.5 fix — detection now finds it."""
        v = _mp4(tmp_path, "clip")
        (tmp_path / "clip.mp3").write_bytes(b"")
        p = _project(tmp_path, Segment(id="s", video=str(v)))
        layout = lay_out(p, probe=lambda _p: 5000)
        files = channel_files_for_layout(p, layout, "mp3")
        assert files == [tmp_path / "clip.mp3"]

    def test_mp3_in_estim_subfolder_resolves(self, tmp_path: Path):
        """Restim workflow: video moved into estim/, mp3 lives there too."""
        estim = tmp_path / "estim"
        estim.mkdir()
        v = _mp4(estim, "0")
        (estim / "0.mp3").write_bytes(b"")
        # When detect_folder is called on tmp_path, it falls back to
        # the subfolder for the video and audio_estim_for_stem also
        # scans subfolders — but here we test the channel resolution
        # directly with the segment pointing at the moved video.
        p = _project(tmp_path, Segment(id="s", video=str(v)))
        layout = lay_out(p, probe=lambda _p: 5000)
        files = channel_files_for_layout(p, layout, "mp3")
        assert files == [estim / "0.mp3"]

    def test_multi_channel_mp3_detected(self, tmp_path: Path):
        """FunscriptForge emits per-channel MP3 (`0.mp3` for main,
        `0.prostate.mp3` for prostate). v0.0.5 detection picks up
        every channel; the engine emits one combined output per."""
        v = _mp4(tmp_path, "0")
        (tmp_path / "0.mp3").write_bytes(b"")
        (tmp_path / "0.prostate.mp3").write_bytes(b"")
        (tmp_path / "0.alpha-prostate.mp3").write_bytes(b"")
        p = _project(tmp_path, Segment(id="s", video=str(v)))
        layout = lay_out(p, probe=lambda _p: 1000)
        from forgeassembler_core.concat_audio_estim import (
            discover_channels_in_layout,
        )
        channels = discover_channels_in_layout(p, layout)
        # Sorted, with the channel suffix preserved.
        assert "mp3" in channels
        assert "prostate.mp3" in channels
        assert "alpha-prostate.mp3" in channels

    def test_both_per_channel_wav_and_mp3_emit_independently(self, tmp_path: Path):
        """When BOTH `clip.stereostim.wav` and `clip.mp3` exist, BOTH
        get emitted as independent channels. Forge produces every
        channel any segment carries; the downstream player picks what
        its hardware needs at playback time."""
        v = _mp4(tmp_path, "clip")
        _stim(tmp_path, "clip", ".stereostim.wav")
        (tmp_path / "clip.mp3").write_bytes(b"")
        p = _project(tmp_path, Segment(id="s", video=str(v)))
        layout = lay_out(p, probe=lambda _p: 1000)
        # Both resolve.
        assert channel_has_any_audio(p, layout, "stereostim.wav")
        assert channel_has_any_audio(p, layout, "mp3")


# ── Output codec depends on output file extension ─────────────────────
class TestOutputCodec:
    def test_mp3_output_uses_libmp3lame(self, tmp_path: Path):
        v = _mp4(tmp_path, "clip")
        (tmp_path / "clip.mp3").write_bytes(b"")
        p = _project(tmp_path, Segment(id="s", video=str(v)))
        layout = lay_out(p, probe=lambda _p: 1000)
        out = str(tmp_path / "combined.mp3")
        cmd = build_audio_estim_command(p, layout, "mp3", out)
        assert "libmp3lame" in cmd.output_args
        # Bitrate is set; PCM args (which are wav-only) are absent.
        assert "-b:a" in cmd.output_args
        assert "pcm_s16le" not in cmd.output_args

    def test_wav_output_uses_pcm(self, tmp_path: Path):
        v = _mp4(tmp_path, "clip")
        _stim(tmp_path, "clip", ".stereostim.wav")
        p = _project(tmp_path, Segment(id="s", video=str(v)))
        layout = lay_out(p, probe=lambda _p: 1000)
        out = str(tmp_path / "combined.stereostim.wav")
        cmd = build_audio_estim_command(p, layout, "stereostim.wav", out)
        assert "pcm_s16le" in cmd.output_args
        assert "libmp3lame" not in cmd.output_args
