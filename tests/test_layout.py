# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Unit tests for the layout engine: computes running timeline."""

from __future__ import annotations

from pathlib import Path

from forgeassembler_core.layout import lay_out
from forgeassembler_core.project import Joiner, Project, Segment


def test_single_segment():
    p = Project(items=[Segment(id="s1", video="a.mp4")])
    layout = lay_out(p, probe=lambda _p: 1000)
    assert len(layout.items) == 1
    assert layout.items[0].start_ms == 0
    assert layout.items[0].end_ms == 1000
    assert layout.total_duration_ms == 1000


def test_two_segments_with_none_joiner():
    p = Project(items=[
        Segment(id="s1", video="a.mp4"),
        Joiner(id="j1", joiner_type="none"),
        Segment(id="s2", video="b.mp4"),
    ])
    layout = lay_out(p, probe=lambda _p: 1000)
    assert layout.total_duration_ms == 2000
    assert [i.start_ms for i in layout.items] == [0, 1000, 1000]


def test_fade_to_black_adds_duration():
    p = Project(items=[
        Segment(id="s1", video="a.mp4"),
        Joiner(id="j1", joiner_type="fade_to_black", params={"duration_s": 2.0}),
        Segment(id="s2", video="b.mp4"),
    ])
    layout = lay_out(p, probe=lambda _p: 1000)
    # 1000 + 2000 + 1000
    assert layout.total_duration_ms == 4000


def test_probe_called_per_segment():
    calls: list[Path] = []

    def probe(path: Path) -> int:
        calls.append(path)
        return 500

    p = Project(items=[
        Segment(id="s1", video="x.mp4"),
        Segment(id="s2", video="y.mp4"),
    ])
    # Note: two segments with no joiner between them is technically a
    # validation error, but the layout engine tolerates it for previews.
    lay_out(p, probe=probe)
    assert [c.name for c in calls] == ["x.mp4", "y.mp4"]
