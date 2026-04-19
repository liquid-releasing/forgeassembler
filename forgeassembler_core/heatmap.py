# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Per-channel funscript heatmap PNGs.

A heatmap is a wide-but-short strip where each horizontal pixel is a
time bucket across the whole script, and the colour encodes the peak
speed (pos units per second) of actions falling in that bucket. The
gradient follows the OpenFunscripter / XBVR convention:

    0         → dark blue   (quiet)
    50-200    → blue / cyan / green
    200-400   → yellow / orange
    400+      → red          (hot)

Pillow is a transitive dep via matplotlib; we use it directly rather
than pulling a plotting library into the render path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from PIL import Image

__all__ = [
    "compute_peak_speeds",
    "heatmap_color",
    "render_heatmap",
    "write_heatmap",
]

# (speed_threshold_pos_per_s, (r, g, b)) pairs — piecewise linear.
_GRADIENT: tuple[tuple[float, tuple[int, int, int]], ...] = (
    (0,   (30, 30, 80)),      # dark blue — quiet
    (50,  (30, 100, 180)),    # blue
    (120, (30, 180, 150)),    # cyan-green
    (200, (120, 200, 30)),    # yellow-green
    (300, (240, 200, 30)),    # yellow
    (400, (240, 120, 30)),    # orange
    (600, (240, 30, 30)),     # red — maxed out
)


def heatmap_color(speed_pos_per_s: float) -> tuple[int, int, int]:
    """Return the (r, g, b) colour for a single speed value.

    Input is clamped to the gradient endpoints; intermediate values
    interpolate linearly between the surrounding stops.
    """
    s = max(0.0, min(_GRADIENT[-1][0], speed_pos_per_s))
    for (s0, c0), (s1, c1) in zip(_GRADIENT[:-1], _GRADIENT[1:]):
        if s <= s1:
            span = s1 - s0 if s1 > s0 else 1.0
            t = (s - s0) / span
            return (
                int(round(c0[0] + t * (c1[0] - c0[0]))),
                int(round(c0[1] + t * (c1[1] - c0[1]))),
                int(round(c0[2] + t * (c1[2] - c0[2]))),
            )
    return _GRADIENT[-1][1]


def compute_peak_speeds(
    actions: Sequence[dict],
    bucket_count: int,
    total_ms: int,
) -> list[float]:
    """Return peak speed (pos units / sec) per time bucket.

    For each adjacent pair of actions, the signal speed on that segment
    is assigned to every bucket it touches. Buckets with no signal stay
    at 0.0. Empty or degenerate input returns an all-zero list.
    """
    if total_ms <= 0 or bucket_count <= 0 or len(actions) < 2:
        return [0.0] * max(bucket_count, 0)

    bucket_ms = total_ms / bucket_count
    peak = [0.0] * bucket_count
    sorted_actions = sorted(actions, key=lambda a: int(a["at"]))
    for prev, curr in zip(sorted_actions[:-1], sorted_actions[1:]):
        dt_ms = int(curr["at"]) - int(prev["at"])
        if dt_ms <= 0:
            continue
        dpos = abs(int(curr["pos"]) - int(prev["pos"]))
        speed = dpos * 1000.0 / dt_ms
        b_start = max(0, int(int(prev["at"]) / bucket_ms))
        b_end = min(bucket_count - 1, int(int(curr["at"]) / bucket_ms))
        for b in range(b_start, b_end + 1):
            if speed > peak[b]:
                peak[b] = speed
    return peak


def render_heatmap(
    actions: Sequence[dict],
    duration_ms: int,
    width: int = 2000,
    height: int = 60,
) -> Image.Image:
    """Return a Pillow Image of the heatmap strip.

    One horizontal pixel = one bucket; colour derived from peak speed
    via `heatmap_color`. Degenerate inputs render an all-dark-blue strip.
    """
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive")
    speeds = compute_peak_speeds(actions, bucket_count=width, total_ms=duration_ms)
    img = Image.new("RGB", (width, height), heatmap_color(0))
    pixels = img.load()
    for x in range(width):
        color = heatmap_color(speeds[x])
        for y in range(height):
            pixels[x, y] = color  # type: ignore[index]
    return img


def write_heatmap(
    actions: Sequence[dict],
    duration_ms: int,
    path: str | Path,
    width: int = 2000,
    height: int = 60,
) -> None:
    """Render and save the heatmap PNG at `path`."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    img = render_heatmap(actions, duration_ms, width=width, height=height)
    img.save(str(p), format="PNG")
