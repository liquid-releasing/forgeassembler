# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""MP4 chapter markers via the ffmetadata format.

Each **Section** contributes exactly one chapter (v2.0 model). The
chapter name comes from `Section.chapter_name()` — explicit
section.name → first segment's bookmark → prettified filename stem
(underscores → spaces, timestamp/hash suffix stripped). A chapter's
time span starts at the section's first segment and runs until the
next section starts (or the project ends).

Output is written as an ffmetadata text file, consumed by ffmpeg as
`-f ffmetadata -i chapters.txt -map_metadata N`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional

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


def _branding_chapter_name(seg) -> str:
    """What to call the closing branding in the chapter list.

    A bookmark someone CHOSE wins. A bookmark that merely repeats the
    filename was derived rather than chosen -- importing a bumper fills it
    in automatically -- and a chapter called `liquidreleasingexit` is worse
    for a viewer than a plain, predictable "End". Measured on a real project:
    both branding segments carried exactly that kind of bookmark.

    So the filename is not a fallback here, unlike `Section.chapter_name`.
    A scene's filename usually describes the scene; a studio bumper's
    filename is an asset slug.
    """
    from pathlib import Path as _Path

    bookmark = (seg.bookmark or "").strip()
    if not bookmark:
        return "End"
    stem = _Path(seg.video).stem if seg.video else ""
    derived = bookmark.casefold() == stem.casefold()
    return "End" if derived else bookmark


def build_chapters(project: "Project", layout: "Layout") -> list[Chapter]:
    """Return one Chapter per Section in the project, in timeline order.

    A section's chapter starts on its **title card** when it has one, and
    on its first segment otherwise, running through to the next section's
    start (or the project's total duration for the last section).

    A title card announces the section it introduces, so skipping to a
    chapter has to land ON the card — landing just past it hides the one
    frame that says where you are. A `fade_to_black` is the opposite: it
    is the previous section leaving, not this one arriving, so it stays
    absorbed into the preceding chapter's tail.

    Either way the chapters remain contiguous, so player UIs still
    navigate directly between sections with nothing falling in a gap.
    """
    from .project import Joiner as _Joiner, Segment as _Seg
    # Map each item id to its start_ms so we can look up section
    # boundaries without re-walking the layout.
    seg_start: dict[str, int] = {}
    joiner_start: dict[str, int] = {}
    for li in layout.items:
        if isinstance(li.item, _Seg):
            seg_start[li.item.id] = li.start_ms  # type: ignore[union-attr]
        elif isinstance(li.item, _Joiner):
            joiner_start[li.item.id] = li.start_ms  # type: ignore[union-attr]

    # Collect the timeline start of each non-empty section.
    sec_starts: list[tuple[int, object]] = []  # (start_ms, Section)
    for sec in project.sections:
        if not sec.segments:
            continue
        first_id = sec.segments[0].id
        if first_id not in seg_start:
            continue
        start = seg_start[first_id]
        lead = sec.leading_joiner
        if lead.joiner_type == "title_card" and lead.id in joiner_start:
            start = joiner_start[lead.id]
        sec_starts.append((start, sec))

    # The closing branding gets a chapter of its own, unlike the opening.
    # That asymmetry is the point: nobody skips TO a studio bumper at the
    # front, but the one at the back is where the credits are, and a viewer
    # who wants them needs somewhere to jump. It also stops the last scene's
    # chapter running on through the bumper to the end of the file.
    outro = project.output.branding_outro
    outro_start: Optional[int] = None
    if outro is not None and outro.id in seg_start:
        outro_start = seg_start[outro.id]

    chapters: list[Chapter] = []
    for i, (start, sec) in enumerate(sec_starts):
        if i + 1 < len(sec_starts):
            end = sec_starts[i + 1][0]
        elif outro_start is not None:
            end = outro_start
        else:
            end = layout.total_duration_ms
        chapters.append(Chapter(
            name=sec.chapter_name(),  # type: ignore[attr-defined]
            start_ms=start,
            end_ms=end,
        ))

    if outro_start is not None:
        chapters.append(Chapter(
            name=_branding_chapter_name(outro),
            start_ms=outro_start,
            end_ms=layout.total_duration_ms,
        ))
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
