# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""MP4 chapter markers via the ffmetadata format.

Each Segment contributes exactly one chapter. The chapter name is
`segment.bookmark` if set, otherwise the video file's stem (so a
new-project scan of 16 folders produces 16 named chapters without any
manual editing). A chapter's time span covers the segment plus any
joiner time that follows — the next chapter starts at the next
segment's start.

Output is written as an ffmetadata text file, consumed by ffmpeg as
`-f ffmetadata -i chapters.txt -map_metadata N`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .layout import Layout
    from .project import Project

__all__ = [
    "Chapter",
    "build_chapters",
    "write_ffmetadata",
]


@dataclass
class Chapter:
    name: str
    start_ms: int
    end_ms: int


def build_chapters(project: "Project", layout: "Layout") -> list[Chapter]:
    """Return one Chapter per Segment in the project, in layout order.

    - Name: `segment.bookmark` if set, else `Path(segment.video).stem`
    - Span: from `segment.start_ms` to the next segment's `start_ms`
      (or `layout.total_duration_ms` for the last segment), so chapter
      durations absorb any intervening joiner time.
    """
    from .project import Segment as _Seg
    seg_items = [li for li in layout.items if isinstance(li.item, _Seg)]
    chapters: list[Chapter] = []
    for i, li in enumerate(seg_items):
        seg = li.item
        # type: ignore[union-attr]
        bookmark = (seg.bookmark or "").strip()  # type: ignore[union-attr]
        name = bookmark or Path(seg.video).stem  # type: ignore[union-attr]
        start = li.start_ms
        if i + 1 < len(seg_items):
            end = seg_items[i + 1].start_ms
        else:
            end = layout.total_duration_ms
        chapters.append(Chapter(name=name, start_ms=start, end_ms=end))
    return chapters


def write_ffmetadata(chapters: list[Chapter], path: str | Path) -> None:
    """Write `chapters` to `path` in ffmetadata 1 format.

    The file always starts with the `;FFMETADATA1` header ffmpeg
    requires. TIMEBASE is 1/1000 so START/END are plain milliseconds.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [";FFMETADATA1", ""]
    for ch in chapters:
        lines.append("[CHAPTER]")
        lines.append("TIMEBASE=1/1000")
        lines.append(f"START={ch.start_ms}")
        lines.append(f"END={ch.end_ms}")
        # ffmetadata key=value: backslash-escape = and ; and # and \
        safe_name = (
            ch.name.replace("\\", "\\\\")
            .replace("=", "\\=")
            .replace(";", "\\;")
            .replace("#", "\\#")
            .replace("\n", "\\\n")
        )
        lines.append(f"title={safe_name}")
        lines.append("")
    p.write_text("\n".join(lines), encoding="utf-8")
