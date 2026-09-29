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

from .channels import funscript_relpath, heatmap_relpath

if TYPE_CHECKING:  # avoid circular at runtime
    from .layout import Layout
    from .project import Project, Segment

__all__ = [
    "FunscriptPart",
    "channels_for_segment",
    "concat_funscripts",
    "detected_channels",
    "forge_funscripts",
    "read_funscript",
    "write_funscript",
]

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
            at = int(a["at"])
            # A part occupies [0, duration_ms) of the output and nothing
            # more. An action outside that window describes footage that is
            # not in the result, so it cannot play where it claims to —
            # and at a hard cut it lands on top of the NEXT scene.
            #
            # This is not hypothetical. A funscript can outlast its own
            # video: one real bundle's motion track ends at 5,592,934ms
            # while the video probes at 5,592,730ms, a 204ms overhang
            # (the track was authored against a duration measured
            # differently from ffmpeg's). Concatenating two of those with
            # a cut put the second scene's opening actions BEFORE the
            # first scene's closing ones. The final sort then interleaved
            # them, and an 18ms gap between two actions 26 units apart
            # read as 1,444 units/s — a lurch no content contains.
            #
            # A joiner's hold hides this by putting seconds of margin at
            # the seam, so it only bites on cuts.
            if at < 0 or at >= part.duration_ms:
                continue
            out_actions.append({
                "at": at + offset_ms,
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
def _lookup_channel(available: dict[str, "Path | str"], key: str):
    """Find `key` in `available`, falling back across station attribution.

    A compilation mixes sources. A `.forge` scene contributes STATION-QUALIFIED
    keys (`estim3p:alpha`); a plain video with a funscript beside it
    contributes a bare `alpha`, because nothing on disk says which device it
    was clamped for. Without a fallback the joined `estim3p:alpha` track would
    silence-fill the loose clip's whole stretch while its alpha file sat right
    there unused.

    So a qualified key falls back to the bare channel, and a bare key accepts
    any station's copy (deterministically, by station name). One alpha file
    feeding two station tracks is the honest reading: it is the same alpha
    data, and the per-device clamping happened upstream in FunscriptForge.
    """
    if key in available:
        return available[key]
    from .channels import channel_of, make_key, parse_key

    station, channel = parse_key(key)
    if station:
        return available.get(channel)
    for other in sorted(available):
        if other != key and channel_of(other) == channel:
            return available[other]
    return available.get(make_key(None, channel))


def _resolve_funscript_path_for_segment(
    segment: "Segment", channel: str,
) -> Optional[Path]:
    """Return the on-disk funscript path for `segment`'s `channel`, or
    None if this segment contributes no actions for that channel.

    `channel` is a channel KEY, so it may be station-qualified.
    """
    if segment.funscripts_source == "none":
        return None
    if segment.funscripts_source == "explicit":
        raw = _lookup_channel(segment.explicit_funscripts, channel)
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
    found = funscripts_for_stem(folder, video_path.stem)
    path = _lookup_channel(found, channel)
    return Path(path) if path else None


def _trim_funscript_window(
    fs: dict, trim_start_ms: int, trim_end_ms: Optional[int],
) -> dict:
    """Return a funscript whose actions are restricted to
    `[trim_start_ms, trim_end_ms)` and shifted so the window starts at 0.

    Untrimmed segments (start=0, end=None) get a no-op return with the
    original dict. Used so a trimmed segment contributes only the
    actions inside its visible window — otherwise actions outside the
    trim would land at wrong absolute times after concat.
    """
    if trim_start_ms == 0 and trim_end_ms is None:
        return fs
    actions = fs.get("actions") or []
    out_actions: list[dict] = []
    for a in actions:
        try:
            at = int(a["at"])
        except (KeyError, TypeError, ValueError):
            continue
        if at < trim_start_ms:
            continue
        if trim_end_ms is not None and at >= trim_end_ms:
            continue
        out_actions.append({"at": at - trim_start_ms, "pos": int(a["pos"])})
    new_fs = dict(fs)
    new_fs["actions"] = out_actions
    return new_fs


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
            # Trim narrows the funscript to the segment's visible window
            # and shifts its actions back to 0 (so concat's running
            # offset puts them at the right absolute time).
            fs = _trim_funscript_window(
                fs, item.trim_start_ms(), item.trim_end_ms(),
            )
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


def channels_for_segment(segment: "Segment") -> set[str]:
    """Every funscript channel `segment` can contribute, by name.

    Mirrors `_resolve_funscript_path_for_segment`'s three sources so the
    two can never disagree about what a segment carries.
    """
    if segment.funscripts_source == "none":
        return set()
    if segment.funscripts_source == "explicit":
        return {ch for ch, raw in segment.explicit_funscripts.items() if raw}
    if segment.is_still():
        return set()  # PNG/title-card segments carry no funscripts
    from .detect import funscripts_for_stem
    video_path = Path(segment.video)
    folder = (
        Path(segment.funscripts_folder)
        if segment.funscripts_folder else video_path.parent
    )
    try:
        return set(funscripts_for_stem(folder, video_path.stem))
    except OSError:
        return set()


def detected_channels(project: "Project") -> set[str]:
    """The union of every funscript channel present on any segment."""
    from .project import Segment as _Seg
    found: set[str] = set()
    # Every segment on the TIMELINE, branding included: an intro bumper
    # carries its own funscripts -- that is what makes it usable to calibrate
    # a device before any content plays -- and a channel only it has still
    # needs a track in the combined output.
    for item in project.timeline_segments():
        if isinstance(item, _Seg):
            found |= channels_for_segment(item)
    return found


# Group (as `categorize_channels` buckets them) -> the OutputChannels field
# that can veto it. "other" deliberately has no toggle: a channel we have no
# category for still rides through, because concatenating `volume` is the
# same operation as concatenating `alpha`.
_GROUP_VETO: dict[str, str] = {
    "main": "main",
    "multi_axis": "multi_axis",
    "three_phase_estim": "three_phase_estim",
    # `four_phase_estim` existed on OutputChannels with nothing mapped to it,
    # so the toggle was inert while e1..e4 rode through under "other".
    "four_phase_estim": "four_phase_estim",
    "prostate": "prostate",
    "pulse_frequency": "pulse_frequency",
}

# Emission order, so a forge is reproducible. Read against the channel INSIDE
# a key, so `estim3p:alpha` and `focstim:alpha` sort together and then by
# station. Anything not named here sorts alphabetically after these.
_CHANNEL_ORDER: tuple[str, ...] = (
    "main",
    "pitch", "roll", "surge", "sway", "twist",
    "alpha", "beta",
    "alpha-prostate", "beta-prostate",
    "pulse_frequency",
)


def _selected_channels(project: "Project") -> list[str]:
    """Which channel KEYS this forge should write, in emission order.

    DETECTION drives the list -- every channel found on the clips is
    produced, which is the promise the Output tab makes. `OutputChannels`
    is a set of VETOES over that, not an allow-list: the old allow-list
    silently dropped 10 of the 20 channels a real FunscriptForge scene
    ships (volume, frequency, pulse_rise_time, handy, shaker, ...).

    Channels with no actions anywhere are still skipped downstream by
    `forge_funscripts`, so nothing empty gets written either way.

    Where each key is WRITTEN is `channels.funscript_relpath`'s business — a
    station's channels go in that device's folder, because three stations now
    write `alpha` and one flat name cannot hold them all.
    """
    from .channels import channel_of
    from .detect import categorize_channels

    oc = project.output_channels
    found = detected_channels(project)
    if not found:
        return []
    groups = categorize_channels({ch: Path(ch) for ch in found})

    allowed: set[str] = set()
    for group, members in groups.items():
        veto_field = _GROUP_VETO.get(group)
        if veto_field is not None and not getattr(oc, veto_field, True):
            continue
        allowed |= set(members)

    def order_key(key: str) -> tuple[int, str, str]:
        channel = channel_of(key)
        try:
            return (_CHANNEL_ORDER.index(channel), "", key)
        except ValueError:
            return (len(_CHANNEL_ORDER), channel, key)

    return sorted(allowed, key=order_key)


def forge_funscripts(
    project: "Project",
    layout: "Layout",
    output_folder: Optional[str | Path] = None,
    basename: Optional[str] = None,
) -> list[Path]:
    """Write one funscript per selected channel; return the written paths.

    `forge_funscripts_map` is the same work keyed by channel, for callers
    that need to know WHICH channel each file is — the `.forge` writer has to
    place them by station.
    """
    return list(
        forge_funscripts_map(project, layout, output_folder, basename).values()
    )


def forge_funscripts_map(
    project: "Project",
    layout: "Layout",
    output_folder: Optional[str | Path] = None,
    basename: Optional[str] = None,
) -> dict[str, Path]:
    """Write one funscript per selected channel; return `{channel key: path}`.

    Channels with zero actions across every segment are skipped (no empty
    file written), which is why the caller cannot predict the map from
    `_selected_channels` alone. If `output_folder` / `basename` are omitted,
    the project's Output settings are used.
    """
    folder = Path(output_folder or project.output.folder or "")
    if not folder:
        raise ValueError("output_folder is required (pass it or set project.output.folder)")
    stem = basename or project.output.basename or "combined"

    # Heatmaps live alongside the .funscript files. Imported here to
    # keep the import optional for environments that don't have Pillow.
    from .heatmap import write_heatmap

    # The MP4's chapter list, in the funscript's own shape. Built once and
    # applied to every channel so all outputs of one forge agree.
    from .chapters import build_chapters
    chapters_for_funscript: list[dict] | None = [
        {"name": c.name, "startTime": c.start_ms, "endTime": c.end_ms}
        for c in build_chapters(project, layout)
    ]

    written: dict[str, Path] = {}
    total_duration_ms = layout.total_duration_ms
    for channel in _selected_channels(project):
        parts = _build_parts_for_channel(project, layout, channel)
        if not any(p.funscript.get("actions") for p in parts):
            continue  # nothing to write for this channel
        combined = concat_funscripts(parts)
        # ONE chapter derivation for both outputs. `concat_funscripts` is
        # pure and marks a chapter per bookmarked part, but the MP4 takes
        # its chapters from `build_chapters`, which works per SECTION. The
        # two disagreed: a 2-clip / 1-section compilation got 2 chapters in
        # the funscript and 1 in the video. Override with the same list the
        # video uses so a player and an editor can never show different
        # chapters for the same forge.
        if chapters_for_funscript is not None:
            if chapters_for_funscript:
                combined["chapters"] = chapters_for_funscript
            else:
                combined.pop("chapters", None)
        # One folder per device, mirroring a FunscriptForge loose export —
        # `E-Stim/`, `FOC-Stim/`, `MultiFunPlayer/` — with the universal
        # stroke script at the top. Flat names cannot hold this any more:
        # three stations write `alpha`. The grouped layout tucks those device
        # folders under `estim/` and `haptic/`; `funscript_relpath` owns both.
        # NOT `layout` -- that name is taken here by the TIMELINE layout.
        folder_layout = project.output.folder_layout
        out_path = folder / funscript_relpath(channel, stem, folder_layout)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        write_funscript(out_path, combined)
        written[channel] = out_path

        # Companion heatmap beside its funscript — except the main one, which
        # grouped sends to `art/`.
        heatmap_path = folder / heatmap_relpath(channel, stem, folder_layout)
        heatmap_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            write_heatmap(
                combined.get("actions") or [],
                total_duration_ms,
                heatmap_path,
            )
        except Exception:  # noqa: BLE001
            # Never let a heatmap failure take down a funscript forge.
            pass
    return written
