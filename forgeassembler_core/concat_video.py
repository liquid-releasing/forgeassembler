# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Build and run the ffmpeg video-forge command.

Two entry points:

- `build_ffmpeg_command(project, layout)` — **pure**. Returns a
  declarative `FfmpegCommand` describing every input, the
  filter_complex graph, mapping, and output args. No subprocess, no
  disk I/O. Callable from tests without ffmpeg installed.
- `forge_video(project, layout)` — composes `build_ffmpeg_command` and
  spawns ffmpeg. Returns the path of the produced MP4.

Fade-to-black semantics
-----------------------
A `fade_to_black` joiner with `duration_s = d` contributes:
  - a `d / 2` fade-out on the tail of the previous segment (capped at
    `_MAX_FADE_S`),
  - a solid black bridge clip of `d` seconds,
  - a `d / 2` fade-in on the head of the next segment.

Total added output time = `d`, matching the layout engine.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .filters import (
    SCALE_FLAGS as _SCALE_FLAGS,
    bug_overlay_filter,
    bug_prepare_filter,
    concat_filter,
    image_overlay_filter,
    loudnorm_filter,
    normalize_segment_filter,
    text_overlay_filter,
)
from .joiners import instantiate as instantiate_joiner
from .layout import Layout
from .project import (
    RESOLUTION_PIXELS,
    Joiner as ProjectJoiner,
    Project,
    Segment,
)

# Legacy default for the per-side fade when a loaded project pre-dates
# the explicit `fade_s` param. Kept so old JSON files render with a
# subtle fade; new projects set `fade_s` explicitly (default 1.0) via
# the FadeToBlack joiner's params_schema.
_LEGACY_FADE_S: float = 0.5


# ── Declarative command description ───────────────────────────────────
@dataclass
class FfmpegInput:
    path: str
    pre_args: list[str] = field(default_factory=list)


@dataclass
class FfmpegCommand:
    inputs: list[FfmpegInput]
    filter_complex: str
    map_video: Optional[str]
    map_audio: Optional[str]
    output_args: list[str]
    output_path: str

    def to_argv(self, ffmpeg_exe: str = "ffmpeg") -> list[str]:
        argv: list[str] = [ffmpeg_exe]
        for inp in self.inputs:
            argv.extend(inp.pre_args)
            argv.extend(["-i", inp.path])
        argv.extend(["-filter_complex", self.filter_complex])
        if self.map_video:
            argv.extend(["-map", self.map_video])
        if self.map_audio:
            argv.extend(["-map", self.map_audio])
        argv.extend(self.output_args)
        argv.extend(["-y", self.output_path])
        return argv


# ── Internal helpers ──────────────────────────────────────────────────
def _resolve_resolution(
    project: Project,
    override: Optional[tuple[int, int]] = None,
) -> tuple[int, int]:
    if override is not None:
        return override
    res = project.output.resolution
    if res == "source":
        raise ValueError(
            "output.resolution='source' requires resolution_override; "
            "probe the first segment before building the command.",
        )
    pixels = RESOLUTION_PIXELS.get(res)
    if pixels is None:
        raise ValueError(f"No pixel dims for resolution {res!r}")
    return pixels


def _resolve_frame_rate(
    project: Project,
    override: Optional[int] = None,
) -> int:
    if override is not None:
        return override
    fps = project.output.fps()
    if fps is None:
        raise ValueError(
            "output.frame_rate='source' requires frame_rate_override; "
            "probe the first video segment before building the command.",
        )
    return fps


def _fade_duration_s(joiner: ProjectJoiner) -> float:
    """Return the per-side fade duration (seconds) for a fade_to_black joiner.

    Reads `fade_s` from the joiner's params (new in the decoupled
    fade/hold model). Legacy projects that predate the split — they
    only have `duration_s` — get the old 0.5s default so their output
    renders with the subtle fade they used to have.
    """
    if joiner.joiner_type != "fade_to_black":
        return 0.0
    inst = instantiate_joiner(joiner.joiner_type, joiner.params)
    if hasattr(inst, "fade_s") and "fade_s" in joiner.params:
        return float(inst.fade_s())  # type: ignore[no-any-return]
    return _LEGACY_FADE_S


def _neighbor_joiners(
    items: list,
    index: int,
) -> tuple[Optional[ProjectJoiner], Optional[ProjectJoiner]]:
    """Return (joiner_before, joiner_after) for the item at `index`."""
    before = items[index - 1] if index > 0 else None
    after = items[index + 1] if index + 1 < len(items) else None
    return (
        before if isinstance(before, ProjectJoiner) else None,
        after if isinstance(after, ProjectJoiner) else None,
    )


def _section_time_windows(project: Project, layout: Layout) -> list[tuple]:
    """Return `[(Section, start_ms, end_ms), ...]` — one row per
    non-empty section, in order.

    A section's window starts at its first segment's `start_ms` in the
    layout and runs to the next section's first segment's `start_ms`
    (so the window absorbs any trailing transition joiner time). The
    last section runs to `layout.total_duration_ms`. Sections whose
    segments don't appear in the layout (shouldn't happen in practice)
    are skipped silently.
    """
    seg_start: dict[str, int] = {}
    for li in layout.items:
        if isinstance(li.item, Segment):
            seg_start[li.item.id] = li.start_ms
    sec_starts: list[tuple] = []  # [(start_ms, Section)]
    for sec in project.sections:
        if not sec.segments:
            continue
        first_id = sec.segments[0].id
        if first_id in seg_start:
            sec_starts.append((seg_start[first_id], sec))

    out: list[tuple] = []
    for i, (start, sec) in enumerate(sec_starts):
        end = (
            sec_starts[i + 1][0]
            if i + 1 < len(sec_starts)
            else layout.total_duration_ms
        )
        out.append((sec, start, end))
    return out


def _fade_filter_chain(
    head_fade_s: float, tail_fade_s: float, duration_s: float,
) -> list[str]:
    """Build the comma-separated `fade=...` chain for a video segment."""
    chain: list[str] = []
    if head_fade_s > 0:
        chain.append(f"fade=t=in:st=0:d={head_fade_s:g}")
    if tail_fade_s > 0:
        start = max(0.0, duration_s - tail_fade_s)
        chain.append(f"fade=t=out:st={start:g}:d={tail_fade_s:g}")
    return chain


def _afade_filter_chain(
    head_fade_s: float, tail_fade_s: float, duration_s: float,
) -> list[str]:
    """Build the comma-separated `afade=...` chain for a segment's audio."""
    chain: list[str] = []
    if head_fade_s > 0:
        chain.append(f"afade=t=in:st=0:d={head_fade_s:g}")
    if tail_fade_s > 0:
        start = max(0.0, duration_s - tail_fade_s)
        chain.append(f"afade=t=out:st={start:g}:d={tail_fade_s:g}")
    return chain


# ── Pure command builder ──────────────────────────────────────────────
def build_ffmpeg_command(
    project: Project,
    layout: Layout,
    output_path: Optional[str] = None,
    resolution_override: Optional[tuple[int, int]] = None,
    frame_rate_override: Optional[int] = None,
    frame_cache: Optional[dict[str, str]] = None,
    chapters_path: Optional[str] = None,
    segments_with_audio: Optional[set[str]] = None,
    text_files: Optional[dict[str, str]] = None,
    encoder: Optional[str] = None,
) -> FfmpegCommand:
    """Return an `FfmpegCommand` describing the video forge for this project.

    `frame_cache` maps a Segment.id to the filesystem path of its
    pre-extracted previous-last-frame PNG (required for any segment with
    `background='previous_last_frame'`). `forge_video` populates this via
    a pre-pass; tests can pass a synthetic dict.

    `frame_rate_override` supplies the encode fps when
    `output.frame_rate == 'source'` (probed from the first video segment
    by `forge_video`; tests can pass a literal int).

    `chapters_path` is an optional path to a pre-written ffmetadata
    file; when supplied, it's added as an input and `-map_metadata` is
    pointed at it so the output MP4 carries chapter markers.

    `segments_with_audio` is an optional set of Segment.ids known to
    contain an audio stream. When supplied, any segment NOT in the set
    with `audio.mode == 'keep'` silently falls back to silence so the
    filtergraph doesn't reference a missing `[N:a]` stream. Default
    (None) = assume every segment has audio (back-compat for tests).
    """
    frame_cache = frame_cache or {}
    out = project.output
    if not out.produce_video:
        raise ValueError(
            "build_ffmpeg_command called but output.produce_video is False",
        )

    if output_path is None:
        if not out.folder:
            raise ValueError("output.folder is required to build a command")
        output_path = str(Path(out.folder) / f"{out.basename}.mp4")

    width, height = _resolve_resolution(project, resolution_override)
    fps = _resolve_frame_rate(project, frame_rate_override)

    segment_layouts = [li for li in layout.items if li.is_segment]
    if not segment_layouts:
        raise ValueError("Project has no segments")

    items = project.items

    # Per-segment head/tail fade durations based on adjacent joiners.
    seg_fades: dict[str, tuple[float, float]] = {}
    for idx, item in enumerate(items):
        if not isinstance(item, Segment):
            continue
        before, after = _neighbor_joiners(items, idx)
        head = _fade_duration_s(before) if before else 0.0
        tail = _fade_duration_s(after) if after else 0.0
        seg_fades[item.id] = (head, tail)

    # ── Stage A: declare inputs (segment video + optional replacement audio).
    inputs: list[FfmpegInput] = []
    seg_vi: dict[str, int] = {}   # main / foreground PNG video input index
    seg_bgi: dict[str, int] = {}  # previous-frame background input index
    seg_ai: dict[str, int] = {}
    # Per-segment list of (overlay_index_into_inputs, Overlay) pairs for
    # image overlays. Non-image overlays are skipped entirely in v1.
    seg_overlays: dict[str, list[tuple[int, object]]] = {}
    for li in segment_layouts:
        seg = li.item
        assert isinstance(seg, Segment)
        dur_s = li.duration_ms / 1000.0
        if seg.is_still():
            pre = ["-loop", "1", "-t", f"{dur_s:g}"]
        elif seg.trim_start or seg.trim_end:
            # Trimmed video: -ss seeks the input to the trim-start; -t
            # caps the read at the effective (trimmed) duration. Both
            # before -i so they're INPUT options (fast seek + read cap).
            trim_start_s = seg.trim_start_ms() / 1000.0
            pre = ["-ss", f"{trim_start_s:g}", "-t", f"{dur_s:g}"]
        else:
            pre = []
        seg_vi[seg.id] = len(inputs)
        inputs.append(FfmpegInput(path=seg.video, pre_args=pre))
        # previous_last_frame segments add a second looped PNG input — the
        # extracted frame from the preceding segment.
        if seg.is_still() and seg.background == "previous_last_frame":
            frame_path = frame_cache.get(seg.id)
            if frame_path is None:
                raise ValueError(
                    f"segment {seg.id}: background=previous_last_frame "
                    "requires frame_cache to contain an extracted-frame path.",
                )
            seg_bgi[seg.id] = len(inputs)
            inputs.append(FfmpegInput(
                path=frame_path,
                pre_args=["-loop", "1", "-t", f"{dur_s:g}"],
            ))
        # Image overlays on this segment (logo, lower-third, etc.).
        # Each one becomes a looped PNG input.
        seg_ov_entries: list[tuple[int, object]] = []
        for ov in seg.overlays:
            if ov.type != "image":
                continue  # text overlays deferred to a later phase
            if not ov.file:
                continue
            seg_ov_entries.append((len(inputs), ov))
            inputs.append(FfmpegInput(
                path=ov.file,
                pre_args=["-loop", "1", "-t", f"{dur_s:g}"],
            ))
        seg_overlays[seg.id] = seg_ov_entries
        if seg.audio.mode == "replace":
            if not seg.audio.file:
                raise ValueError(
                    f"segment {seg.id}: audio.mode=replace but audio.file missing",
                )
            # Always cap replacement audio at the segment's duration.
            # Stills need -t to have any duration at all; real videos need
            # -t so that audio longer than the video doesn't desync the
            # concat (the audio gets truncated to match video length).
            aud_pre = ["-t", f"{dur_s:g}"]
            seg_ai[seg.id] = len(inputs)
            inputs.append(FfmpegInput(path=seg.audio.file, pre_args=aud_pre))

    # ── Stage B: per-segment normalize + audio + fades.
    filter_parts: list[str] = []
    seg_pair: dict[str, tuple[str, str]] = {}
    for i, li in enumerate(segment_layouts):
        seg = li.item
        assert isinstance(seg, Segment)
        dur_s = li.duration_ms / 1000.0
        vidx = seg_vi[seg.id]
        head_s, tail_s = seg_fades[seg.id]

        # Video: either single-input normalize, or two-input composite
        # (previous_last_frame: background + foreground PNG).
        if seg.is_still() and seg.background == "previous_last_frame":
            bg_idx = seg_bgi[seg.id]
            v_bg = f"v_bg{i}"
            # Normalize the extracted frame to canonical WxH. No color
            # temperature applied here — it's applied after composite.
            filter_parts.append(normalize_segment_filter(
                in_label=f"{bg_idx}:v",
                out_label=v_bg,
                width=width,
                height=height,
            ))
            # Composite the design PNG (vidx) onto the background,
            # centered, preserving its alpha via format=auto.
            v_composed = f"v_composed{i}"
            filter_parts.append(
                f"[{v_bg}][{vidx}:v]"
                f"overlay=x=(W-w)/2:y=(H-h)/2:format=auto"
                f"[{v_composed}]",
            )
            if seg.color_temperature_k is not None:
                v_norm = f"v_norm{i}"
                filter_parts.append(
                    f"[{v_composed}]"
                    f"colortemperature=temperature={seg.color_temperature_k}"
                    f"[{v_norm}]",
                )
            else:
                v_norm = v_composed
        else:
            # Single-input normalize (default path).
            v_norm = f"v_norm{i}"
            filter_parts.append(normalize_segment_filter(
                in_label=f"{vidx}:v",
                out_label=v_norm,
                width=width,
                height=height,
                color_temperature_k=seg.color_temperature_k,
            ))

        # Per-segment image overlays (logos, lower-thirds, captions, …).
        # Each overlay composites onto the current base, becoming the new
        # base for the next overlay. Applied BEFORE the head/tail fade so
        # overlays fade together with the segment at transitions.
        v_after_overlays = v_norm
        for j, (ov_idx, ov) in enumerate(seg_overlays[seg.id]):
            v_after = f"v_ov_{i}_{j}"
            filter_parts.append(image_overlay_filter(
                in_video_label=v_after_overlays,
                in_image_label=f"{ov_idx}:v",
                out_label=v_after,
                position=ov.position,  # type: ignore[arg-type]
                start_s=ov.start_s,  # type: ignore[arg-type]
                end_s=ov.end_s,  # type: ignore[arg-type]
                opacity=ov.opacity,  # type: ignore[arg-type]
                fade_in_s=ov.fade_in_s,  # type: ignore[arg-type]
                fade_out_s=ov.fade_out_s,  # type: ignore[arg-type]
            ))
            v_after_overlays = v_after

        v_label = v_after_overlays
        v_fade_chain = _fade_filter_chain(head_s, tail_s, dur_s)
        if v_fade_chain:
            v_label = f"v_seg{i}"
            filter_parts.append(
                f"[{v_after_overlays}]{','.join(v_fade_chain)}[{v_label}]",
            )

        # Audio: source depends on mode; stills get silence unless replaced.
        a_base = f"a_base{i}"
        if seg.audio.mode == "replace":
            aidx = seg_ai[seg.id]
            filter_parts.append(
                f"[{aidx}:a]aresample=48000,aformat=channel_layouts=stereo"
                f"[{a_base}]",
            )
        elif seg.audio.mode == "silence" or seg.is_still():
            filter_parts.append(
                f"anullsrc=d={dur_s:g}:r=48000:cl=stereo[{a_base}]",
            )
        elif seg.audio.mode == "keep":
            # If the caller told us this clip has no audio stream (or
            # we're conservative: the set was supplied and this segment
            # isn't in it), synthesize silence so `[N:a]` isn't
            # referenced against a stream ffmpeg can't find.
            has_audio = (
                segments_with_audio is None
                or seg.id in segments_with_audio
            )
            if has_audio:
                filter_parts.append(
                    f"[{vidx}:a]aresample=48000,aformat=channel_layouts=stereo"
                    f"[{a_base}]",
                )
            else:
                filter_parts.append(
                    f"anullsrc=d={dur_s:g}:r=48000:cl=stereo[{a_base}]",
                )
        else:
            raise ValueError(f"Unknown audio mode: {seg.audio.mode!r}")

        a_label = a_base
        a_fade_chain = _afade_filter_chain(head_s, tail_s, dur_s)
        if a_fade_chain:
            a_label = f"a_seg{i}"
            filter_parts.append(
                f"[{a_base}]{','.join(a_fade_chain)}[{a_label}]",
            )

        seg_pair[seg.id] = (v_label, a_label)

    # ── Stage C: walk items, assembling the concat-pair list.
    # Insert a solid black bridge for each fade_to_black joiner.
    concat_pairs: list[tuple[str, str]] = []
    bridge_idx = 0
    for item in items:
        if isinstance(item, Segment):
            concat_pairs.append(seg_pair[item.id])
            continue
        # Joiner
        assert isinstance(item, ProjectJoiner)
        if item.joiner_type == "fade_to_black":
            joiner_inst = instantiate_joiner(item.joiner_type, item.params)
            d_ms = joiner_inst.duration_ms()
            d_s = d_ms / 1000.0
            # Hold == 0 means pure crossfade through black — the
            # adjacent segments still get fade-out / fade-in, but
            # there's no solid bridge between them. Skip the color
            # source and anullsrc entirely; ffmpeg refuses a color
            # source with d=0.
            if d_s > 0:
                bridge_color = joiner_inst.color()  # '#rrggbb' or '#000000'
                v_bridge = f"v_bridge{bridge_idx}"
                a_bridge = f"a_bridge{bridge_idx}"
                bridge_idx += 1
                # ffmpeg `color` source takes 0xRRGGBB hex; strip the '#'.
                filter_parts.append(
                    f"color=c=0x{bridge_color.lstrip('#')}:s={width}x{height}:"
                    f"d={d_s:g}:r={fps}[{v_bridge}]",
                )
                filter_parts.append(
                    f"anullsrc=d={d_s:g}:r=48000:cl=stereo[{a_bridge}]",
                )
                concat_pairs.append((v_bridge, a_bridge))
        # "none" joiner: no bridge, concat handles it naturally.

    # ── Stage D: concat (skipped when there's only one pair).
    if len(concat_pairs) == 1:
        final_v, final_a = concat_pairs[0]
    else:
        final_v, final_a = "vconcat", "aconcat"
        filter_parts.append(concat_filter(concat_pairs, final_v, final_a))

    # ── Stage D.5: section-level image overlays.
    # Each overlay is timed relative to its section's start in the
    # final timeline, then applied on top of the concat'd video before
    # the project-level bug lands on top of everything.
    section_overlay_count = 0
    for sec, sec_start_ms, sec_end_ms in _section_time_windows(project, layout):
        for ov in sec.overlays:
            if ov.kind != "image":
                continue  # audio overlays land in the audio pipeline (future)
            abs_start_s = (sec_start_ms / 1000.0) + float(ov.start_s)
            # duration_s == 0 means "play to end of section".
            sec_end_s = sec_end_ms / 1000.0
            if ov.duration_s and ov.duration_s > 0:
                abs_end_s = min(abs_start_s + float(ov.duration_s), sec_end_s)
            else:
                abs_end_s = sec_end_s
            effective_dur = max(0.0, abs_end_s - abs_start_s)
            if effective_dur <= 0:
                continue

            ov_input_idx = len(inputs)
            # -t runs from the start of the input (t=0 of the concat'd
            # timeline) through abs_end_s so the looped image is still
            # alive when the enable window opens at abs_start_s. Using
            # `effective_dur` here was the old bug: the image stream
            # ended at t=effective_dur, which for any later section is
            # long before enable activates.
            inputs.append(FfmpegInput(
                path=ov.file,
                pre_args=["-loop", "1", "-t", f"{abs_end_s:g}"],
            ))
            # Pre-scale the image at scale_pct before feeding it into
            # the overlay helper. 100 = native; anything else gets a
            # separate filter node so the overlay can reference the
            # scaled label. `format=rgba` *before* scale forces the
            # scaler to interpolate with an alpha channel; without it,
            # ffmpeg can pick a YUV intermediate and the PNG's
            # transparent background becomes opaque after scaling.
            image_label = f"{ov_input_idx}:v"
            if int(ov.scale_pct) != 100:
                scaled_label = f"v_secov{section_overlay_count}_scaled"
                ratio = ov.scale_pct / 100.0
                filter_parts.append(
                    f"[{image_label}]"
                    f"format=rgba,"
                    f"scale=iw*{ratio:g}:ih*{ratio:g}:flags={_SCALE_FLAGS},"
                    f"setsar=1"
                    f"[{scaled_label}]",
                )
                image_label = scaled_label

            out_label = f"v_secov{section_overlay_count}"
            filter_parts.append(image_overlay_filter(
                in_video_label=final_v,
                in_image_label=image_label,
                out_label=out_label,
                position=ov.position,
                start_s=abs_start_s,
                end_s=abs_end_s,
                opacity=ov.opacity,
                fade_in_s=ov.fade_in_s,
                fade_out_s=ov.fade_out_s,
            ))
            final_v = out_label
            section_overlay_count += 1

    # ── Stage D.6: section-level text overlays (drawtext).
    # Rendered AFTER image overlays so text can sit on top of a logo
    # or banner. Same absolute-time enable window as images.
    text_overlay_count = 0
    for sec, sec_start_ms, sec_end_ms in _section_time_windows(project, layout):
        for ov in sec.overlays:
            if ov.kind != "text":
                continue
            if not ov.text:
                continue  # blank text → nothing to draw
            abs_start_s = (sec_start_ms / 1000.0) + float(ov.start_s)
            sec_end_s = sec_end_ms / 1000.0
            if ov.duration_s and ov.duration_s > 0:
                abs_end_s = min(abs_start_s + float(ov.duration_s), sec_end_s)
            else:
                abs_end_s = sec_end_s
            if abs_end_s <= abs_start_s:
                continue

            # Resolve the font stem to a full path. When the stem
            # doesn't match any installed font (font was set on a
            # different machine, user hasn't picked one yet), fall
            # back to the first available system font so the text
            # still renders. If no fonts are installed at all, skip
            # the overlay with no filter emitted.
            from .fonts import list_fonts, resolve_font_path
            fontfile = resolve_font_path(ov.font_family) if ov.font_family else None
            if fontfile is None:
                all_fonts = list_fonts()
                if not all_fonts:
                    continue  # no fonts on this machine
                fontfile = all_fonts[0][1]

            out_label = f"v_sectx{text_overlay_count}"
            # Prefer the pre-written textfile when available (runtime
            # path). Inline text= is kept for tests and for legacy
            # projects without a pre-pass.
            textfile_path = None
            if text_files is not None:
                textfile_path = text_files.get(ov.id)
            filter_parts.append(text_overlay_filter(
                in_video_label=final_v,
                out_label=out_label,
                text=ov.text,
                textfile=textfile_path,
                fontfile=fontfile,
                font_size=ov.font_size,
                font_color=ov.text_color,
                position=ov.position,
                start_s=abs_start_s,
                end_s=abs_end_s,
                opacity=ov.opacity,
                fade_in_s=ov.fade_in_s,
                fade_out_s=ov.fade_out_s,
            ))
            final_v = out_label
            text_overlay_count += 1

    # ── Stage D.75: section-level audio overlays (mix into main).
    # For each audio overlay: register an audio input; resample/delay
    # it to the section-relative start; apply fades; scale to mix_pct;
    # duck the main audio during the overlay window by the complementary
    # share (so a 50% mix drops the main to 50% while the overlay
    # plays); then amix the two streams with duration=first so the
    # main audio's length governs the output.
    audio_overlay_count = 0
    for sec, sec_start_ms, sec_end_ms in _section_time_windows(project, layout):
        for ov in sec.overlays:
            if ov.kind != "audio":
                continue
            abs_start_s = (sec_start_ms / 1000.0) + float(ov.start_s)
            sec_end_s = sec_end_ms / 1000.0
            if ov.duration_s and ov.duration_s > 0:
                abs_end_s = min(abs_start_s + float(ov.duration_s), sec_end_s)
            else:
                abs_end_s = sec_end_s
            effective_dur = max(0.0, abs_end_s - abs_start_s)
            if effective_dur <= 0:
                continue

            aov_idx = len(inputs)
            # `-t` truncates on read; input file shorter than the
            # window naturally ends on its own.
            inputs.append(FfmpegInput(
                path=ov.file,
                pre_args=["-t", f"{effective_dur:g}"],
            ))

            mix_share = max(0.0, min(1.0, ov.mix_pct / 100.0))
            clip_share = 1.0 - mix_share

            # Build the overlay's prep chain.
            ov_label = f"a_secov{audio_overlay_count}"
            chain: list[str] = [
                "aresample=48000",
                "aformat=channel_layouts=stereo",
            ]
            delay_ms = int(round(abs_start_s * 1000))
            if delay_ms > 0:
                chain.append(f"adelay={delay_ms}|{delay_ms}")
            if ov.fade_in_s > 0:
                chain.append(
                    f"afade=t=in:st={abs_start_s:g}:d={ov.fade_in_s:g}",
                )
            if ov.fade_out_s > 0:
                fo_start = max(abs_start_s, abs_end_s - float(ov.fade_out_s))
                chain.append(
                    f"afade=t=out:st={fo_start:g}:d={ov.fade_out_s:g}",
                )
            # Apply the overlay's gain last so fades operate at full range.
            if mix_share < 1.0:
                chain.append(f"volume={mix_share:g}")
            filter_parts.append(
                f"[{aov_idx}:a]{','.join(chain)}[{ov_label}]",
            )

            # Duck the main audio during the overlay window (only when
            # the clip share is less than 1.0 — at 100% overlay mix the
            # main is muted in-window).
            if clip_share < 1.0:
                dim_label = f"a_main_dim{audio_overlay_count}"
                filter_parts.append(
                    f"[{final_a}]volume={clip_share:g}:"
                    f"enable='between(t,{abs_start_s:g},{abs_end_s:g})'"
                    f"[{dim_label}]",
                )
                final_a = dim_label

            mixed_label = f"a_mixed{audio_overlay_count}"
            # normalize=0 keeps the per-leg gains we just applied;
            # duration=first caps the mix to the main's length so the
            # video controls overall timing (user's rule).
            filter_parts.append(
                f"[{final_a}][{ov_label}]"
                f"amix=inputs=2:normalize=0:duration=first"
                f"[{mixed_label}]",
            )
            final_a = mixed_label
            audio_overlay_count += 1

    # ── Stage E: project-level bug overlay.
    if out.bug is not None:
        bug_input_idx = len(inputs)
        inputs.append(FfmpegInput(
            path=out.bug.file,
            pre_args=[
                "-loop", "1",
                "-t", f"{layout.total_duration_ms / 1000.0:g}",
            ],
        ))
        filter_parts.append(bug_prepare_filter(
            f"{bug_input_idx}:v", "bug_rgba", out.bug.opacity,
        ))
        filter_parts.append(bug_overlay_filter(
            final_v, "bug_rgba", "v_bugged",
            out.bug.corner, out.bug.margin_px,
        ))
        final_v = "v_bugged"

    # ── Stage F: final loudness normalize.
    if out.normalize_audio:
        filter_parts.append(loudnorm_filter(final_a, "a_loud"))
        final_a = "a_loud"

    # ── Stage G: closing fade-to-black (applied to video AND audio in
    # lockstep). Starts at `total - duration_s` and ends at the tail of
    # the output so the picture and sound close together. The bug, if
    # present, also fades out because this runs after the bug overlay.
    if out.closing_joiner.joiner_type == "fade_to_black":
        # Prefer `fade_s` (new decoupled model); fall back to
        # `duration_s` for legacy projects that predate the split.
        # Hold (`duration_s` in the new model) is irrelevant for
        # closing — there's no section after to fade INTO, so we just
        # fade out the tail of existing content.
        close_params = out.closing_joiner.params
        if "fade_s" in close_params:
            close_d_s = float(close_params.get("fade_s", 1.0))
        else:
            close_d_s = float(close_params.get("duration_s", 1.0))
        total_s = layout.total_duration_ms / 1000.0
        fade_start_s = max(0.0, total_s - close_d_s)
        filter_parts.append(
            f"[{final_v}]"
            f"fade=t=out:st={fade_start_s:g}:d={close_d_s:g}"
            f"[v_close]",
        )
        final_v = "v_close"
        filter_parts.append(
            f"[{final_a}]"
            f"afade=t=out:st={fade_start_s:g}:d={close_d_s:g}"
            f"[a_close]",
        )
        final_a = "a_close"

    filter_complex = ";\n".join(filter_parts)

    # Chapters: extra ffmetadata input supplies MP4 chapter markers.
    # Added last so every media input keeps its original index.
    if chapters_path is not None:
        chapters_idx = len(inputs)
        inputs.append(FfmpegInput(
            path=chapters_path,
            pre_args=["-f", "ffmetadata"],
        ))
    else:
        chapters_idx = None

    output_args = [
        *_video_codec_args(out, fps, encoder),
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
    ]

    # Pull global metadata (chapters) from the ffmetadata input. Must
    # come before the per-key `-metadata` overrides so they win.
    if chapters_idx is not None:
        output_args.extend(["-map_metadata", str(chapters_idx)])

    # Container metadata. User-set fields first; ForgeAssembler signs
    # the output with its version as the encoder tag.
    from .about import APP_NAME, VERSION
    for key, value in out.metadata.non_empty_items():
        output_args.extend(["-metadata", f"{key}={value}"])
    output_args.extend(["-metadata", f"encoder={APP_NAME} {VERSION}"])

    return FfmpegCommand(
        inputs=inputs,
        filter_complex=filter_complex,
        map_video=f"[{final_v}]",
        map_audio=f"[{final_a}]",
        output_args=output_args,
        output_path=output_path,
    )


# ── ffmpeg invocation ─────────────────────────────────────────────────
# ── Video encoder selection (CPU x264 ↔ GPU hardware) ─────────────────
#
# The encode is the hot, all-cores-pinned part of a forge. When a supported
# GPU is present we offload it to the vendor's dedicated hardware encoder:
# faster, and it keeps the CPU (and a thermally-limited laptop) far cooler.
# A GPU is NOT required — with none detected we fall back to libx264 on the
# CPU, which always works. Selection is auto by default; override with the
# FORGEASSEMBLER_ENCODER env var (nvenc | qsv | amf | x264).
#
# Supported hardware encoders (H.264):
#   nvenc  → h264_nvenc   NVIDIA NVENC     (GeForce / RTX / Quadro)
#   qsv    → h264_qsv     Intel Quick Sync (Arc / recent iGPUs)
#   amf    → h264_amf     AMD AMF/VCE      (Radeon)
#   x264   → libx264      CPU software     (universal fallback)
_HW_ENCODER_FFNAME = {
    "nvenc": "h264_nvenc",
    "qsv":   "h264_qsv",
    "amf":   "h264_amf",
}
# Auto-detect priority — first that actually encodes on this machine wins.
_HW_ENCODER_PRIORITY = ("nvenc", "qsv", "amf")
_ENCODER_CACHE: dict[str, str] = {}


def _video_codec_args(out, fps, encoder: Optional[str] = None) -> list[str]:
    """Video `-c:v …` args for the chosen encoder.

    `encoder` is one of nvenc/qsv/amf (hardware) or None/x264/libx264 (CPU).
    Hardware encoders map ForgeAssembler's H.264 CRF onto their nearest
    constant-quality control so the quality preset stays meaningful; None keeps
    the deterministic libx264 path (what the pure builder + tests expect).
    """
    crf = out.crf()
    enc = (encoder or "libx264").lower()
    tail = ["-pix_fmt", "yuv420p", "-r", str(fps)]
    if enc in ("nvenc", "h264_nvenc"):
        # NVENC: VBR constant-quality; -cq mirrors x264 CRF closely. p5 ≈ medium.
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr",
                "-cq", str(crf), "-b:v", "0", *tail]
    if enc in ("qsv", "h264_qsv"):
        return ["-c:v", "h264_qsv", "-global_quality", str(crf),
                "-preset", "medium", *tail]
    if enc in ("amf", "h264_amf"):
        return ["-c:v", "h264_amf", "-rc", "cqp", "-qp_i", str(crf),
                "-qp_p", str(crf), "-quality", "balanced", *tail]
    # CPU fallback (also the default for unknown ids) — unchanged behaviour.
    return ["-c:v", "libx264", "-preset", "medium", "-crf", str(crf), *tail]


def _probe_encoder(exe: str, enc_id: str) -> bool:
    """True when `enc_id`'s hardware encoder actually encodes on this machine.

    Compiled-in ≠ usable (no GPU, driver missing, laptop MUX quirks), so we run
    a sub-second test encode of a synthetic clip and check it exits cleanly."""
    name = _HW_ENCODER_FFNAME.get(enc_id)
    if not name:
        return False
    try:
        argv = [exe, "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "testsrc=d=0.2:s=256x144:r=10",
                "-c:v", name, "-f", "null", "-"]
        return subprocess.run(argv, capture_output=True, timeout=25).returncode == 0
    except Exception:
        return False


def resolve_video_encoder(ffmpeg_exe: Optional[str] = None) -> str:
    """Pick the best available video encoder for THIS machine.

    Order: explicit FORGEASSEMBLER_ENCODER override → auto-detect the fastest
    working GPU encoder (nvenc → qsv → amf) → libx264 CPU fallback. The probe
    result is cached per ffmpeg binary so a multi-pass forge probes once."""
    override = os.environ.get("FORGEASSEMBLER_ENCODER", "").strip().lower()
    if override in ("x264", "libx264", "cpu"):
        return "libx264"
    if override in _HW_ENCODER_FFNAME:
        return override  # trust an explicit hardware choice; probe stays for auto
    exe = ffmpeg_exe or _resolve_ffmpeg_exe()
    if exe in _ENCODER_CACHE:
        return _ENCODER_CACHE[exe]
    chosen = "libx264"
    for cand in _HW_ENCODER_PRIORITY:
        if _probe_encoder(exe, cand):
            chosen = cand
            break
    _ENCODER_CACHE[exe] = chosen
    return chosen


def _resolve_ffmpeg_exe() -> str:
    """Locate an ffmpeg binary.

    Prefers the static binary shipped with imageio-ffmpeg (same pattern
    as ForgeYT), falling back to a PATH lookup.
    """
    try:
        import imageio_ffmpeg  # type: ignore[import-not-found]
    except ImportError:
        pass
    else:
        return imageio_ffmpeg.get_ffmpeg_exe()
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    raise RuntimeError(
        "No ffmpeg available. Install imageio-ffmpeg "
        "(`pip install imageio-ffmpeg`) or put ffmpeg on PATH.",
    )


def _find_preceding_segment(items: list, index: int) -> Optional[Segment]:
    """Return the last Segment appearing before `index` in `items`, or None."""
    for j in range(index - 1, -1, -1):
        candidate = items[j]
        if isinstance(candidate, Segment):
            return candidate
    return None


def _extract_last_frame(
    video_path: str, output_png: str, ffmpeg_exe: str,
) -> None:
    """Extract the last frame of a video to a PNG via ffmpeg.

    Uses `-sseof -0.5` to seek half a second from the end, then grabs a
    single frame. Fast and reliable for normal H.264 content.
    """
    result = subprocess.run(
        [
            ffmpeg_exe,
            "-hide_banner",
            "-loglevel", "error",
            "-sseof", "-0.5",
            "-i", str(video_path),
            "-update", "1",
            "-frames:v", "1",
            "-y",
            str(output_png),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg could not extract last frame of {video_path!r}: "
            f"{result.stderr}",
        )


def _build_text_files(
    project: Project, temp_dir: Path,
) -> dict[str, str]:
    """Write each text overlay's content to a tempfile under
    `temp_dir` and return a dict of SectionOverlay.id -> file path.

    Using drawtext's `textfile=` at forge time sidesteps all the
    inline-escape traps — real newlines in the user's text become
    real line breaks in the rendered output, and apostrophes /
    colons / percents need no escaping at the filter_complex layer.
    """
    files: dict[str, str] = {}
    for sec in project.sections:
        for ov in sec.overlays:
            if ov.kind != "text":
                continue
            if not ov.text:
                continue
            path = temp_dir / f"text_{ov.id}.txt"
            # Normalize line endings to `\n` and write bytes so Python's
            # Windows newline translation doesn't leave `\r\n` in the
            # file — a stray `\r` renders in drawtext as a tall
            # invisible glyph, bloating line spacing.
            normalized = ov.text.replace("\r\n", "\n").replace("\r", "\n")
            path.write_bytes(normalized.encode("utf-8"))
            files[ov.id] = str(path)
    return files


def _build_frame_cache(
    project: Project, ffmpeg_exe: str, temp_dir: Path,
) -> dict[str, str]:
    """Extract the previous-segment last frame for every
    `previous_last_frame` segment. Returns a dict of Segment.id ->
    PNG path. If the preceding segment is itself a still image, we
    copy the PNG rather than re-encoding via ffmpeg.
    """
    cache: dict[str, str] = {}
    for idx, item in enumerate(project.items):
        if not isinstance(item, Segment):
            continue
        if item.background != "previous_last_frame":
            continue
        prev = _find_preceding_segment(project.items, idx)
        if prev is None:
            raise ValueError(
                f"segment {item.id}: background=previous_last_frame has no "
                "preceding segment to extract from.",
            )
        out_png = temp_dir / f"{item.id}__prev_frame.png"
        if prev.is_still():
            shutil.copyfile(prev.video, out_png)
        else:
            _extract_last_frame(prev.video, str(out_png), ffmpeg_exe)
        cache[item.id] = str(out_png)
    return cache


def _resolve_source_frame_rate(
    project: Project, ffmpeg_exe: str,
) -> Optional[int]:
    """When `output.frame_rate == 'source'`, probe the first real video
    segment via ffmpeg and return its fps rounded to the nearest integer.
    Returns None when the frame_rate is a fixed value (no probe needed)
    or when the project has no video segments to probe.
    """
    if project.output.fps() is not None:
        return None
    first_video = next(
        (s for s in project.segments() if not s.is_still()),
        None,
    )
    if first_video is None:
        return None
    from .probe import probe_frame_rate_fps
    fps = probe_frame_rate_fps(first_video.video, ffmpeg_exe)
    return int(round(fps))


def forge_video(
    project: Project,
    layout: Layout,
    ffmpeg_exe: Optional[str] = None,
    output_path: Optional[str] = None,
    resolution_override: Optional[tuple[int, int]] = None,
    frame_rate_override: Optional[int] = None,
    log_callback: Optional[Callable[[str], None]] = None,
) -> Path:
    """Run ffmpeg to produce the output MP4. Returns the output path.

    Handles the `previous_last_frame` pre-pass: before the main forge,
    the last frame of each relevant preceding segment is extracted to
    a temp directory, which is cleaned up on exit.

    Raises `RuntimeError` if ffmpeg exits non-zero.
    """
    exe = ffmpeg_exe or _resolve_ffmpeg_exe()

    # When the project asks for 'source' fps, probe first video segment.
    # Explicit override from the caller always wins.
    if frame_rate_override is None:
        frame_rate_override = _resolve_source_frame_rate(project, exe)

    temp_dir = Path(tempfile.mkdtemp(prefix="forgeassembler_"))
    try:
        frame_cache = _build_frame_cache(project, exe, temp_dir)
        text_files = _build_text_files(project, temp_dir)

        # Probe each non-still segment for an audio stream. Segments
        # without one (phone captures, silent loops, animation renders)
        # would otherwise fail the filtergraph with
        # "Stream specifier ':a' matches no streams".
        from .probe import probe_has_audio_stream
        segments_with_audio: set[str] = set()
        for seg in project.segments():
            if seg.is_still():
                continue
            if seg.audio.mode != "keep":
                continue  # replace/silence don't reference [N:a]
            try:
                if probe_has_audio_stream(seg.video, exe):
                    segments_with_audio.add(seg.id)
            except Exception:  # noqa: BLE001
                # Conservative: if probing fails, treat as no-audio so
                # we emit silence instead of breaking the encode.
                pass

        # Write chapters to a temp ffmetadata file, to be passed to ffmpeg.
        from .chapters import build_chapters, write_ffmetadata
        chapters = build_chapters(project, layout)
        chapters_path: Optional[str] = None
        if chapters:
            chapters_file = temp_dir / "chapters.ffmetadata"
            write_ffmetadata(chapters, chapters_file)
            chapters_path = str(chapters_file)

        # Offload the encode to a GPU hardware encoder when one is available
        # (cooler + faster); falls back to libx264 on the CPU otherwise.
        encoder = resolve_video_encoder(exe)

        cmd = build_ffmpeg_command(
            project, layout,
            output_path=output_path,
            resolution_override=resolution_override,
            frame_rate_override=frame_rate_override,
            frame_cache=frame_cache,
            chapters_path=chapters_path,
            segments_with_audio=segments_with_audio,
            text_files=text_files,
            encoder=encoder,
        )

        out_path = Path(cmd.output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        argv = cmd.to_argv(exe)
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert proc.stdout is not None
        # Keep a tail of the last N lines so any non-zero exit can
        # surface ffmpeg's own error text in the raised exception.
        # ffmpeg prints most of its complaints right before it dies.
        from collections import deque
        tail: deque[str] = deque(maxlen=60)
        for line in proc.stdout:
            stripped = line.rstrip()
            tail.append(stripped)
            if log_callback:
                log_callback(stripped)
        proc.wait()
        if proc.returncode != 0:
            snippet = "\n".join(tail) if tail else "(no stderr captured)"
            raise RuntimeError(
                f"ffmpeg exited with code {proc.returncode}.\n"
                f"Last {len(tail)} line(s) of ffmpeg output:\n{snippet}",
            )
        return out_path
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
