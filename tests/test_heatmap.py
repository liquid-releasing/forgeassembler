# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Unit tests for heatmap computation + rendering + file output."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from forgeassembler_core.heatmap import (
    compute_peak_speeds,
    heatmap_color,
    render_heatmap,
    write_heatmap,
)


# ── heatmap_color ─────────────────────────────────────────────────────
def test_heatmap_color_zero_is_dark_blue():
    assert heatmap_color(0) == (30, 30, 80)


def test_heatmap_color_max_is_red():
    assert heatmap_color(600) == (240, 30, 30)


def test_heatmap_color_clamps_below_zero():
    # Negatives should clamp to the low end (dark blue).
    assert heatmap_color(-50) == (30, 30, 80)


def test_heatmap_color_clamps_above_max():
    assert heatmap_color(10_000) == (240, 30, 30)


def test_heatmap_color_interpolates_between_stops():
    # Midway between stop 0 (speed=0, dark blue) and stop 1 (speed=50, blue)
    c = heatmap_color(25)
    # Red channel stays at 30 on both stops — should not drift.
    assert c[0] == 30
    # Blue channel moves from 80 → 180 → midway ≈ 130
    assert 125 <= c[2] <= 135


# ── compute_peak_speeds ───────────────────────────────────────────────
def test_compute_speeds_empty_returns_zeros():
    assert compute_peak_speeds([], bucket_count=10, total_ms=1000) == [0.0] * 10


def test_compute_speeds_single_action_returns_zeros():
    # Need at least two points for a speed segment.
    assert compute_peak_speeds(
        [{"at": 0, "pos": 50}], bucket_count=10, total_ms=1000,
    ) == [0.0] * 10


def test_compute_speeds_zero_total_returns_empty_length_zero_buckets():
    # Degenerate total_ms means buckets collapse to 0 regardless.
    assert compute_peak_speeds(
        [{"at": 0, "pos": 0}, {"at": 100, "pos": 100}],
        bucket_count=10, total_ms=0,
    ) == [0.0] * 10


def test_compute_speeds_peak_in_correct_bucket():
    """A single 0→100 jump in 1000ms spans the whole timeline; every
    bucket should record 100 pos/sec as its peak."""
    actions = [{"at": 0, "pos": 0}, {"at": 1000, "pos": 100}]
    speeds = compute_peak_speeds(actions, bucket_count=10, total_ms=1000)
    assert all(abs(s - 100.0) < 0.001 for s in speeds)


def test_compute_speeds_localized_burst():
    """A fast motion only in the last 100ms should leave earlier buckets
    at 0 and the trailing bucket hot."""
    actions = [
        {"at": 0, "pos": 0},          # dwell
        {"at": 900, "pos": 0},
        {"at": 1000, "pos": 100},     # 100 units in 100ms = 1000/s
    ]
    speeds = compute_peak_speeds(actions, bucket_count=10, total_ms=1000)
    # Buckets 0-8 get 0 change (pos stayed at 0); bucket 9 gets 1000/s peak.
    assert speeds[0] == 0.0
    assert speeds[-1] == pytest.approx(1000.0)


def test_compute_speeds_takes_peak_not_average():
    """Two adjacent spans of different speed → peak speed wins for the
    bucket range each span covers."""
    actions = [
        {"at": 0,    "pos": 0},
        {"at": 100,  "pos": 100},  # speed 1000 across [0..100]
        {"at": 1000, "pos": 0},    # speed ~111 across [100..1000]
    ]
    speeds = compute_peak_speeds(actions, bucket_count=10, total_ms=1000)
    # Bucket 0 covers 0-100ms so should see the fast 1000/s
    assert speeds[0] == pytest.approx(1000.0)
    # Later buckets see only the slower span
    assert speeds[-1] < 200


def test_compute_speeds_ignores_unsorted_order():
    actions = [
        {"at": 1000, "pos": 100},
        {"at": 0, "pos": 0},
    ]
    speeds = compute_peak_speeds(actions, bucket_count=10, total_ms=1000)
    assert all(abs(s - 100.0) < 0.001 for s in speeds)


# ── render_heatmap ────────────────────────────────────────────────────
def test_render_heatmap_has_correct_dimensions():
    img = render_heatmap(
        [{"at": 0, "pos": 0}, {"at": 1000, "pos": 100}],
        duration_ms=1000, width=50, height=20,
    )
    assert img.size == (50, 20)
    assert img.mode == "RGB"


def test_render_heatmap_rejects_nonpositive_dims():
    with pytest.raises(ValueError):
        render_heatmap([], 1000, width=0, height=10)
    with pytest.raises(ValueError):
        render_heatmap([], 1000, width=10, height=0)


def test_render_heatmap_empty_uses_base_color():
    """Empty actions → uniform dark-blue strip."""
    img = render_heatmap([], duration_ms=1000, width=20, height=5)
    pixels = img.load()
    for x in range(20):
        for y in range(5):
            assert pixels[x, y] == (30, 30, 80)


def test_render_heatmap_hot_segment_reaches_red():
    """A very fast span at the tail should paint red pixels in the
    bucket range it covers; left edge stays dark blue (dwell pos=0).
    Buckets beyond the final action's timestamp stay quiet too."""
    img = render_heatmap(
        [
            {"at": 0, "pos": 0},
            {"at": 900, "pos": 0},
            {"at": 950, "pos": 100},  # 100 units / 50ms = 2000/s (above 600)
        ],
        duration_ms=1000, width=100, height=3,
    )
    pixels = img.load()
    # bucket_ms = 10; the hot span covers buckets 90..95 inclusive.
    assert pixels[0, 0] == (30, 30, 80)     # quiet at start
    assert pixels[92, 0] == (240, 30, 30)   # red in the hot range
    assert pixels[99, 0] == (30, 30, 80)    # quiet past the last action


# ── write_heatmap ─────────────────────────────────────────────────────
def test_write_heatmap_writes_valid_png(tmp_path: Path):
    out = tmp_path / "preview.png"
    write_heatmap(
        [{"at": 0, "pos": 0}, {"at": 1000, "pos": 100}],
        duration_ms=1000,
        path=out,
        width=30, height=10,
    )
    assert out.is_file()
    # Readable back as a PNG
    with Image.open(out) as img:
        assert img.size == (30, 10)
        assert img.format == "PNG"


def test_write_heatmap_creates_parent_dirs(tmp_path: Path):
    out = tmp_path / "sub" / "dir" / "preview.png"
    write_heatmap([], 1000, out, width=5, height=2)
    assert out.is_file()


# ── forge_funscripts integration: companion .heatmap.png ─────────────
def test_forge_funscripts_writes_heatmap_for_each_channel(tmp_path: Path):
    import json

    from forgeassembler_core.concat_funscript import forge_funscripts
    from forgeassembler_core.layout import lay_out
    from forgeassembler_core.project import (
        Output,
        OutputChannels,
        Project,
        Segment,
    )

    # Build a little clip folder with main + pitch funscripts
    clip_dir = tmp_path / "clip"
    clip_dir.mkdir()
    video = clip_dir / "c.mp4"
    video.write_bytes(b"")
    (clip_dir / "c.funscript").write_text(
        json.dumps({"actions": [{"at": 0, "pos": 0}, {"at": 500, "pos": 100}]}),
        encoding="utf-8",
    )
    (clip_dir / "c.pitch.funscript").write_text(
        json.dumps({"actions": [{"at": 0, "pos": 50}]}),
        encoding="utf-8",
    )

    out_folder = tmp_path / "out"
    p = Project(
        items=[Segment(id="s1", video=str(video))],
        output=Output(folder=str(out_folder), basename="x"),
        output_channels=OutputChannels(main=True, multi_axis=True),
    )
    layout = lay_out(p, probe=lambda _p: 1000)
    written = forge_funscripts(p, layout)

    # One main + one pitch channel (roll/surge/sway/twist are empty → skipped)
    names = sorted(p.name for p in written)
    assert names == ["x.funscript", "x.pitch.funscript"]
    # Each one has a companion .heatmap.png next to it
    assert (out_folder / "x.heatmap.png").is_file()
    assert (out_folder / "x.pitch.heatmap.png").is_file()
    # Empty channels (roll etc.) do NOT produce stray heatmap pngs
    assert not (out_folder / "x.roll.heatmap.png").exists()


def test_forge_funscripts_heatmap_failure_does_not_break_funscript_write(tmp_path: Path):
    """If heatmap rendering throws, the .funscript file is still written
    and forge_funscripts continues to the next channel."""
    import json

    from unittest.mock import patch

    from forgeassembler_core.concat_funscript import forge_funscripts
    from forgeassembler_core.layout import lay_out
    from forgeassembler_core.project import (
        Output,
        OutputChannels,
        Project,
        Segment,
    )

    clip_dir = tmp_path / "clip"
    clip_dir.mkdir()
    video = clip_dir / "c.mp4"
    video.write_bytes(b"")
    (clip_dir / "c.funscript").write_text(
        json.dumps({"actions": [{"at": 0, "pos": 0}]}),
        encoding="utf-8",
    )

    out_folder = tmp_path / "out"
    p = Project(
        items=[Segment(id="s1", video=str(video))],
        output=Output(folder=str(out_folder), basename="x"),
        output_channels=OutputChannels(main=True),
    )
    layout = lay_out(p, probe=lambda _p: 1000)

    with patch(
        "forgeassembler_core.heatmap.write_heatmap",
        side_effect=RuntimeError("PIL blew up"),
    ):
        written = forge_funscripts(p, layout)

    # Funscript still got written
    assert (out_folder / "x.funscript").is_file()
    assert written == [out_folder / "x.funscript"]
    # But no heatmap file (because render failed and we swallow)
    assert not (out_folder / "x.heatmap.png").exists()
