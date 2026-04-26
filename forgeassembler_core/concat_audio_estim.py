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
    "forge_audio_estim",
]

# Output suffix for the combined per-channel WAV. Mirrors detect.py's
# AUDIO_ESTIM_SUFFIXES; the dict key is the engine-internal channel
# name (`stereostim` etc.) and the value is the file suffix appended
# to the project basename (e.g. "combined.stereostim.wav").
AUDIO_ESTIM_CHANNELS: tuple[tuple[str, str], ...] = (
    ("stereostim.wav", ".stereostim.wav"),
    ("legacy.wav", ".legacy.wav"),
    ("prostate.stereostim.wav", ".prostate.stereostim.wav"),
)

# Target rate / layout for every concat. 48 kHz stereo matches the
# video pipeline's audio output, keeps cross-compatibility, and lets
# silence-fill segments mix cleanly with real ones at different
# source rates.
TARGET_SAMPLE_RATE = 48000
TARGET_CHANNEL_LAYOUT = "stereo"


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
    output_args = [
        "-c:a", "pcm_s16le",
        "-ar", str(TARGET_SAMPLE_RATE),
        "-ac", "2",
    ]

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
    for channel_key, file_suffix in AUDIO_ESTIM_CHANNELS:
        if not channel_has_any_audio(project, layout, channel_key):
            continue  # nothing real to write for this channel

        out_path = folder / f"{stem}{file_suffix}"
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
