# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Funscript concatenation: shift timestamps, merge actions, add chapters.

Two entry points mirror the video side:

- `concat_funscripts(parts)` — **pure**. Shifts timestamps, merges, adds
  chapter markers. No disk I/O.
- `forge_funscripts(project, layout)` — walks the project, resolves the
  funscript file for each Segment × channel (auto_detect / explicit /
  none), builds `FunscriptPart`s, concats, and writes one output file
  per selected channel. Returns the written paths.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Optional

if TYPE_CHECKING:  # avoid circular at runtime
    from .layout import Layout
    from .project import Project, Segment

__all__ = [
    "FunscriptPart",
    "concat_funscripts",
    "forge_funscripts",
    "read_funscript",
    "write_funscript",
]

# Channel sets per OutputChannels toggle. Values are (in-detect name,
# filename suffix) pairs. Suffix "" means the plain `{basename}.funscript`.
_CHANNELS_MAIN: tuple[tuple[str, str], ...] = (("main", ""),)
_CHANNELS_MULTI_AXIS: tuple[tuple[str, str], ...] = tuple(
    (axis, f".{axis}") for axis in ("pitch", "roll", "surge", "sway", "twist")
)
_CHANNELS_3PHASE: tuple[tuple[str, str], ...] = (
    ("alpha", ".alpha"), ("beta", ".beta"),
)
_CHANNELS_PROSTATE: tuple[tuple[str, str], ...] = (
    ("alpha-prostate", ".alpha-prostate"),
    ("beta-prostate", ".beta-prostate"),
)


@dataclass
class FunscriptPart:
    """One segment's contribution to the combined funscript."""
    funscript: dict             # parsed JSON {"actions": [...], ...}
    duration_ms: int            # how long this part occupies in the output
    chapter_name: str | None = None  # bookmark label for this segment


def read_funscript(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Funscript is not a JSON object: {path}")
    data.setdefault("actions", [])
    return data


def write_funscript(path: str | Path, funscript: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(funscript, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def concat_funscripts(parts: Iterable[FunscriptPart]) -> dict:
    """Concatenate N funscripts into one.

    Each part's actions get their `at` timestamps shifted by the running
    offset. Chapters are accumulated as `{"name", "startTime", "endTime"}`
    entries (ms).

    Joiner gaps: if a part has no funscript but occupies time, pass a
    FunscriptPart with an empty funscript (`{"actions": []}`) and the
    desired duration. V1 policy is "hold last position" — we do not
    insert synthetic actions; the player will hold between actions
    naturally.
    """
    out_actions: list[dict] = []
    chapters: list[dict] = []
    offset_ms = 0

    for part in parts:
        actions = part.funscript.get("actions") or []
        for a in actions:
            out_actions.append({
                "at": int(a["at"]) + offset_ms,
                "pos": int(a["pos"]),
            })
        if part.chapter_name:
            chapters.append({
                "name": part.chapter_name,
                "startTime": offset_ms,
                "endTime": offset_ms + part.duration_ms,
            })
        offset_ms += part.duration_ms

    # Stable sort in case input wasn't strictly sorted
    out_actions.sort(key=lambda a: a["at"])

    out: dict = {"actions": out_actions}
    if chapters:
        out["chapters"] = chapters
    return out


# ── Project → files orchestration ─────────────────────────────────────
def _resolve_funscript_path_for_segment(
    segment: "Segment", channel: str,
) -> Optional[Path]:
    """Return the on-disk funscript path for `segment`'s `channel`, or
    None if this segment contributes no actions for that channel.
    """
    if segment.funscripts_source == "none":
        return None
    if segment.funscripts_source == "explicit":
        raw = segment.explicit_funscripts.get(channel)
        return Path(raw) if raw else None
    # auto_detect (default): look at siblings of the video file.
    if segment.is_still():
        return None  # PNG/title-card segments carry no funscripts
    from .detect import funscripts_for_stem
    video_path = Path(segment.video)
    folder = (
        Path(segment.funscripts_folder)
        if segment.funscripts_folder else video_path.parent
    )
    return funscripts_for_stem(folder, video_path.stem).get(channel)


def _build_parts_for_channel(
    project: "Project", layout: "Layout", channel: str,
) -> list[FunscriptPart]:
    """Walk the Layout and produce one FunscriptPart per item for a
    single channel. Segments without a matching funscript contribute an
    empty gap of the correct duration — preserving overall timing.
    """
    from .project import Segment as _Seg
    parts: list[FunscriptPart] = []
    for li in layout.items:
        item = li.item
        if isinstance(item, _Seg):
            fs_path = _resolve_funscript_path_for_segment(item, channel)
            if fs_path is not None and fs_path.is_file():
                try:
                    fs = read_funscript(fs_path)
                except (json.JSONDecodeError, ValueError):
                    fs = {"actions": []}
            else:
                fs = {"actions": []}
            parts.append(FunscriptPart(
                funscript=fs,
                duration_ms=li.duration_ms,
                chapter_name=item.bookmark,
            ))
        else:
            # Joiner (none or fade_to_black): empty gap of its duration.
            parts.append(FunscriptPart(
                funscript={"actions": []},
                duration_ms=li.duration_ms,
            ))
    return parts


def _selected_channels(project: "Project") -> list[tuple[str, str]]:
    """Expand OutputChannels toggles into a flat list of (channel, suffix)
    pairs in a deterministic order."""
    oc = project.output_channels
    out: list[tuple[str, str]] = []
    if oc.main:
        out.extend(_CHANNELS_MAIN)
    if oc.multi_axis:
        out.extend(_CHANNELS_MULTI_AXIS)
    if oc.three_phase_estim:
        out.extend(_CHANNELS_3PHASE)
    if oc.prostate:
        out.extend(_CHANNELS_PROSTATE)
    # four_phase_estim / audio_estim / pulse_frequency deferred to Phase 2.
    return out


def forge_funscripts(
    project: "Project",
    layout: "Layout",
    output_folder: Optional[str | Path] = None,
    basename: Optional[str] = None,
) -> list[Path]:
    """Write one funscript file per selected channel; return written paths.

    Channels with zero actions across every segment are skipped (no empty
    file written). If `output_folder` / `basename` are omitted, the
    project's Output settings are used.
    """
    folder = Path(output_folder or project.output.folder or "")
    if not folder:
        raise ValueError("output_folder is required (pass it or set project.output.folder)")
    stem = basename or project.output.basename or "combined"

    written: list[Path] = []
    for channel, suffix in _selected_channels(project):
        parts = _build_parts_for_channel(project, layout, channel)
        if not any(p.funscript.get("actions") for p in parts):
            continue  # nothing to write for this channel
        combined = concat_funscripts(parts)
        out_path = folder / f"{stem}{suffix}.funscript"
        write_funscript(out_path, combined)
        written.append(out_path)
    return written
