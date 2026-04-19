# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Video-duration probing via ffmpeg.

imageio-ffmpeg ships only `ffmpeg`, not `ffprobe`, so we parse ffmpeg's
own stderr for the Duration line rather than requiring a separate probe
binary. Fast because `ffmpeg -i <path>` without any output file exits
immediately (with error), having already printed the stream info.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):([\d.]+)")
# Matches `, 59.94 fps,` or `, 30 fps,` inside a Stream #N:M line.
# ffmpeg prints both `fps` (average) and `tbr` (decoder base rate) — we
# want fps because it's what encoded frames are delivered at.
_FPS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*fps")


def _run_probe(path: str | Path, ffmpeg_exe: str) -> str:
    """Run `ffmpeg -i <path>` and return the full stderr text.

    Non-zero exit is expected here (we gave ffmpeg no output file); we
    just want the stream info it prints on startup.
    """
    result = subprocess.run(
        [ffmpeg_exe, "-hide_banner", "-i", str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stderr or ""


def probe_duration_ms(path: str | Path, ffmpeg_exe: str) -> int:
    """Return the duration of a media file in milliseconds.

    Raises RuntimeError if the duration line can't be found in ffmpeg's
    output (typical for unreadable / unsupported files).
    """
    stderr = _run_probe(path, ffmpeg_exe)
    match = _DURATION_RE.search(stderr)
    if not match:
        raise RuntimeError(
            f"Could not determine duration of {path!r}.\n"
            f"ffmpeg stderr:\n{stderr}",
        )
    hours = int(match.group(1))
    minutes = int(match.group(2))
    seconds = float(match.group(3))
    return int(round((hours * 3600 + minutes * 60 + seconds) * 1000))


def probe_frame_rate_fps(path: str | Path, ffmpeg_exe: str) -> float:
    """Return the video frame rate of `path` in frames per second.

    Raises RuntimeError if no `fps` token can be found in ffmpeg's stream
    info — typically because the file has no video stream or is unreadable.
    """
    stderr = _run_probe(path, ffmpeg_exe)
    # Walk stream lines; take the first Video line's fps value.
    for line in stderr.splitlines():
        if "Video:" not in line:
            continue
        match = _FPS_RE.search(line)
        if match:
            return float(match.group(1))
    raise RuntimeError(
        f"Could not determine frame rate of {path!r}.\n"
        f"ffmpeg stderr:\n{stderr}",
    )


def probe_has_audio_stream(path: str | Path, ffmpeg_exe: str) -> bool:
    """Return True iff `path` declares at least one `Audio:` stream.

    Cheap helper so callers can pre-detect audio-less sources (phone
    captures, silent loops, animation renders) and swap 'keep' audio
    mode for silence. Returns False if the probe can't read the file —
    the safe default for the downstream filtergraph.
    """
    try:
        stderr = _run_probe(path, ffmpeg_exe)
    except OSError:
        return False
    # "Stream #N:M... Audio: codec ..." — only the Audio: anchor is
    # needed; Data/Video lines never have that substring.
    return any("Audio:" in line for line in stderr.splitlines())
