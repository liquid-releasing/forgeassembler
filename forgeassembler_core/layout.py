# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Compute the running timeline of a project.

Given a Project and a way to probe each segment's video duration, produce
a Layout that lists each item with its start/end times in ms. The Layout
is what drives video concat, funscript concat, chapter markers, and the
live preview.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Union

from .joiners import instantiate as instantiate_joiner
from .project import Joiner as ProjectJoiner
from .project import Project, Segment

DurationProbe = Callable[[Path], int]  # returns duration in ms


@dataclass
class LaidOutItem:
    item: Union[Segment, ProjectJoiner]
    start_ms: int
    end_ms: int

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    @property
    def is_segment(self) -> bool:
        return isinstance(self.item, Segment)


@dataclass
class Layout:
    items: list[LaidOutItem]

    @property
    def total_duration_ms(self) -> int:
        return self.items[-1].end_ms if self.items else 0

    def segments(self) -> list[LaidOutItem]:
        return [i for i in self.items if i.is_segment]

    def joiners(self) -> list[LaidOutItem]:
        return [i for i in self.items if not i.is_segment]


def lay_out(project: Project, probe: DurationProbe) -> Layout:
    """Build a Layout from a Project.

    `probe(path)` must return the duration in ms of the video at `path`.
    In tests, pass a stub. In production, pass a function that shells
    to ffprobe.
    """
    out: list[LaidOutItem] = []
    t = 0
    for item in project.items:
        if isinstance(item, Segment):
            duration = probe(Path(item.video))
            out.append(LaidOutItem(item=item, start_ms=t, end_ms=t + duration))
            t += duration
        elif isinstance(item, ProjectJoiner):
            joiner = instantiate_joiner(item.joiner_type, item.params)
            d = joiner.duration_ms()
            out.append(LaidOutItem(item=item, start_ms=t, end_ms=t + d))
            t += d
        else:
            raise TypeError(f"Unknown item type: {type(item)}")
    return Layout(items=out)
