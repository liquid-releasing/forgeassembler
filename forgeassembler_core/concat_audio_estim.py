# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Per-channel haptic-estim audio concat.

restim renders one WAV per channel alongside each clip
(`{stem}.stereostim.wav`, `{stem}.legacy.wav`,
`{stem}.prostate.stereostim.wav`). When `Output.produce_audio_estim`
is on, the forge concatenates these in lockstep with the video — one
combined WAV per channel — silence-filling segments that don't have
a file for that channel and honoring per-segment trim windows.

Two entry points mirror the funscript / video sides:

- `build_audio_estim_command(project, layout, channel_suffix, ...)` —
  **pure**. Returns an `FfmpegCommand` describing the concat for one
  channel. No subprocess, no disk I/O.
- `forge_audio_estim(project, layout)` — composes per-channel
  commands and runs ffmpeg. Returns the list of written WAV paths.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from .concat_video import FfmpegCommand, FfmpegInput

if TYPE_CHECKING:
    from .layout import Layout
    from .project import Project, Segment

__all__ = [
    "AUDIO_ESTIM_CHANNELS",
    "build_audio_estim_command",
    "channel_files_for_layout",
    "discover_channels_in_layout",
    "forge_audio_estim",
]

# Discovery is dynamic. Detection (`audio_estim_for_stem`) returns
# one entry per `{stem}.<channel>.<ext>` file it finds; the engine
# emits one combined output WAV/MP3 per discovered channel. Channel
# keys mirror the file suffix shape:
#
#   `0.mp3`                       → channel "mp3"           → `<basename>.mp3`
#   `0.prostate.mp3`              → channel "prostate.mp3"  → `<basename>.prostate.mp3`
#   `0.alpha-prostate.mp3`        → channel "alpha-prostate.mp3" → `<basename>.alpha-prostate.mp3`
#   `0.stereostim.wav`            → channel "stereostim.wav"   → `<basename>.stereostim.wav`
#   `0.prostate.stereostim.wav`   → channel "prostate.stereostim.wav" → `<basename>.prostate.stereostim.wav`
#
# `AUDIO_ESTIM_CHANNELS` is kept (pinned to the per-channel WAV
# split) for back-compat with v0.0.4 callers / tests; new code uses
# `discover_channels_in_layout()`.
AUDIO_ESTIM_CHANNELS: tuple[tuple[str, str], ...] = (
    ("stereostim.wav", ".stereostim.wav"),
    ("legacy.wav", ".legacy.wav"),
    ("prostate.stereostim.wav", ".prostate.stereostim.wav"),
)

# Target rate / layout for the WAV concat path. 48 kHz stereo matches
# the video pipeline's audio output, keeps cross-compatibility, and
# lets silence-fill segments mix cleanly with real ones at different
# source rates.
TARGET_SAMPLE_RATE = 48000
TARGET_CHANNEL_LAYOUT = "stereo"


def _output_codec_args(output_path: str) -> list[str]:
    """Pick output codec based on the output file extension.

    `.mp3` → libmp3lame at 192 kbit/s 48 kHz stereo. Mirrors typical
    haptic-audio bitrate so the round-trip from .mp3 → concat → .mp3
    doesn't grossly inflate or compress the source. `.wav` (and
    everything else) → 16-bit PCM at 48 kHz stereo. Same defaults
    the engine uses inside the video pipeline's audio path.
    """
    if output_path.lower().endswith(".mp3"):
        return [
            "-c:a", "libmp3lame",
            "-b:a", "192k",
            "-ar", str(TARGET_SAMPLE_RATE),
            "-ac", "2",
        ]
    return [
        "-c:a", "pcm_s16le",
        "-ar", str(TARGET_SAMPLE_RATE),
        "-ac", "2",
    ]


def _resolve_channel_audio_path(
    segment: "Segment", channel_key: str,
) -> Optional[Path]:
    """Return the on-disk audio path for `segment` × `channel_key`, or
    None if this segment contributes silence for that channel.

    Stills carry no haptic audio. Untrimmed and trimmed video segments
    both use the same auto-detect: scan the video's folder (and the
    known subfolders) for `{stem}.{channel_key}` next to the source.
    """
    if segment.is_still():
        return None
    from .detect import audio_estim_for_stem
    video_path = Path(segment.video)
    folder = video_path.parent
    files = audio_estim_for_stem(folder, video_path.stem)
    return files.get(channel_key)


def channel_files_for_layout(
    project: "Project", layout: "Layout", channel_key: str,
) -> list[Optional[Path]]:
    """Return one entry per layout item:
      * Path — the audio file for this segment × channel (if any)
      * None — no audio for this segment (silence-fill) or this is a
        joiner item (which never carries channel audio)
    Order matches `layout.items`.
    """
    from .project import Segment as _Seg
    out: list[Optional[Path]] = []
    for li in layout.items:
        if isinstance(li.item, _Seg):
            out.append(_resolve_channel_audio_path(li.item, channel_key))
        else:
            out.append(None)  # joiner = silence
    return out


def channel_has_any_audio(
    project: "Project", layout: "Layout", channel_key: str,
) -> bool:
    """True iff at least one segment in the layout contributes a real
    audio file for `channel_key`. Used to skip channels that would
    produce a 100%-silent output (saves a pointless empty WAV).
    """
    return any(
        path is not None
        for path in channel_files_for_layout(project, layout, channel_key)
    )


def discover_channels_in_layout(
    project: "Project", layout: "Layout",
) -> list[str]:
    """Walk every segment in `layout` and return every channel key
    any of them carries — sorted, de-duplicated.

    The engine emits one combined output per discovered channel.
    Stills are skipped (no haptic audio). Joiners contribute nothing.
    """
    from .detect import audio_estim_for_stem
    from .project import Segment as _Seg
    channels: set[str] = set()
    for li in layout.items:
        item = li.item
        if not isinstance(item, _Seg):
            continue
        if item.is_still():
            continue
        video_path = Path(item.video)
        if not video_path.exists():
            # Still try the parent's listing — the segment may be on
            # a path that's been moved; we don't want to silently
            # drop its audio just because of a stale Path object.
            channels.update(
                audio_estim_for_stem(video_path.parent, video_path.stem).keys(),
            )
            continue
        channels.update(
            audio_estim_for_stem(video_path.parent, video_path.stem).keys(),
        )
    return sorted(channels)


def build_audio_estim_command(
    project: "Project",
    layout: "Layout",
    channel_key: str,
    output_path: str,
) -> FfmpegCommand:
    """Return an `FfmpegCommand` that concatenates one channel's
    per-segment audio into `output_path`.

    Real audio inputs get `-ss <trim_start> -t <effective_dur>` so
    each contributes only its visible window in lockstep with the
    video. Missing-audio segments and joiner items contribute
    `anullsrc` of the matching duration. All inputs feed an N-way
    `concat=v=0:a=1` filter; the output is encoded as PCM 16-bit
    little-endian at 48 kHz stereo.
    """
    from .project import Segment as _Seg

    inputs: list[FfmpegInput] = []
    filter_parts: list[str] = []
    concat_labels: list[str] = []

    silence_idx = 0
    for i, li in enumerate(layout.items):
        dur_s = li.duration_ms / 1000.0
        item = li.item

        # Resolve the audio file (None = silence-fill / joiner).
        path: Optional[Path] = None
        seg: Optional[_Seg] = None
        if isinstance(item, _Seg):
            seg = item
            path = _resolve_channel_audio_path(item, channel_key)

        if path is not None and seg is not None:
            # Real input: -ss / -t when a trim window is set, just the
            # raw input otherwise. Audio files don't have a "still"
            # case so the trim path is uniform.
            input_idx = len(inputs)
            if seg.trim_start or seg.trim_end:
                trim_start_s = seg.trim_start_ms() / 1000.0
                pre = ["-ss", f"{trim_start_s:g}", "-t", f"{dur_s:g}"]
            else:
                pre = []
            inputs.append(FfmpegInput(path=str(path), pre_args=pre))
            label = f"a_in{i}"
            filter_parts.append(
                f"[{input_idx}:a]"
                f"aresample={TARGET_SAMPLE_RATE},"
                f"aformat=channel_layouts={TARGET_CHANNEL_LAYOUT}"
                f"[{label}]",
            )
            concat_labels.append(label)
        else:
            # Silence-fill: anullsrc lives entirely in the filter graph
            # (no input file), generated for the segment's duration.
            label = f"a_sil{silence_idx}"
            silence_idx += 1
            filter_parts.append(
                f"anullsrc=d={dur_s:g}:r={TARGET_SAMPLE_RATE}:"
                f"cl={TARGET_CHANNEL_LAYOUT}[{label}]",
            )
            concat_labels.append(label)

    if not concat_labels:
        raise ValueError("Project has no items; nothing to concat.")

    if len(concat_labels) == 1:
        final_label = concat_labels[0]
    else:
        final_label = "a_out"
        joined = "".join(f"[{lbl}]" for lbl in concat_labels)
        filter_parts.append(
            f"{joined}concat=n={len(concat_labels)}:v=0:a=1[{final_label}]",
        )

    filter_complex = ";\n".join(filter_parts)
    output_args = _output_codec_args(output_path)

    return FfmpegCommand(
        inputs=inputs,
        filter_complex=filter_complex,
        map_video=None,
        map_audio=f"[{final_label}]",
        output_args=output_args,
        output_path=output_path,
    )


def forge_audio_estim(
    project: "Project",
    layout: "Layout",
    ffmpeg_exe: Optional[str] = None,
    output_folder: Optional[str | Path] = None,
    basename: Optional[str] = None,
) -> list[Path]:
    """Run ffmpeg per channel; return the list of written WAV paths.

    Channels with no audio file in any segment are skipped (a 100%-
    silent output would just waste disk). When `output_folder` /
    `basename` are omitted, the project's `Output` settings are used.
    """
    import subprocess  # noqa: PLC0415

    from .concat_video import _resolve_ffmpeg_exe  # noqa: PLC0415

    exe = ffmpeg_exe or _resolve_ffmpeg_exe()
    folder = Path(output_folder or project.output.folder or "")
    if not folder:
        raise ValueError(
            "output_folder is required (pass it or set project.output.folder)",
        )
    folder.mkdir(parents=True, exist_ok=True)
    stem = basename or project.output.basename or "combined"

    written: list[Path] = []
    for channel_key in discover_channels_in_layout(project, layout):
        # Channel key already encodes the file extension:
        #   "mp3"                       → out: <stem>.mp3
        #   "prostate.mp3"              → out: <stem>.prostate.mp3
        #   "alpha-prostate.mp3"        → out: <stem>.alpha-prostate.mp3
        #   "stereostim.wav"            → out: <stem>.stereostim.wav
        #   "prostate.stereostim.wav"   → out: <stem>.prostate.stereostim.wav
        out_path = folder / f"{stem}.{channel_key}"
        cmd = build_audio_estim_command(
            project, layout, channel_key, str(out_path),
        )
        argv = cmd.to_argv(exe)
        result = subprocess.run(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            tail = "\n".join(result.stdout.splitlines()[-40:])
            raise RuntimeError(
                f"ffmpeg failed concatenating channel {channel_key!r} "
                f"(exit {result.returncode}):\n{tail}",
            )
        written.append(out_path)
    return written
