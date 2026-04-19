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


def probe_duration_ms(path: str | Path, ffmpeg_exe: str) -> int:
    """Return the duration of a media file in milliseconds.

    Raises RuntimeError if the duration line can't be found in ffmpeg's
    output (typical for unreadable / unsupported files).
    """
    result = subprocess.run(
        [ffmpeg_exe, "-hide_banner", "-i", str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    # ffmpeg writes Duration to stderr; exit code is non-zero because
    # we gave it no output file. That's expected — we just want the header.
    match = _DURATION_RE.search(result.stderr or "")
    if not match:
        raise RuntimeError(
            f"Could not determine duration of {path!r}.\n"
            f"ffmpeg stderr:\n{result.stderr}",
        )
    hours = int(match.group(1))
    minutes = int(match.group(2))
    seconds = float(match.group(3))
    return int(round((hours * 3600 + minutes * 60 + seconds) * 1000))
