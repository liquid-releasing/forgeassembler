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

import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .filters import (
    bug_overlay_filter,
    bug_prepare_filter,
    concat_filter,
    image_overlay_filter,
    loudnorm_filter,
    normalize_segment_filter,
)
from .joiners import instantiate as instantiate_joiner
from .layout import Layout
from .project import (
    RESOLUTION_PIXELS,
    Joiner as ProjectJoiner,
    Project,
    Segment,
)

# Cap on the fade-in/out duration applied to segment tails/heads when
# adjacent to a fade_to_black joiner. Longer fades get clipped to keep
# them visually subtle; the solid-black bridge still honours duration_s.
_MAX_FADE_S: float = 0.5

# Hard-coded output frame rate for v1. Later: expose via Project.output.
_FRAME_RATE: int = 30


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


def _fade_duration_s(joiner: ProjectJoiner) -> float:
    """Return the per-side fade duration (seconds) for a fade_to_black joiner."""
    if joiner.joiner_type != "fade_to_black":
        return 0.0
    d_ms = instantiate_joiner(joiner.joiner_type, joiner.params).duration_ms()
    return min((d_ms / 1000.0) / 2.0, _MAX_FADE_S)


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
    frame_cache: Optional[dict[str, str]] = None,
) -> FfmpegCommand:
    """Return an `FfmpegCommand` describing the video forge for this project.

    `frame_cache` maps a Segment.id to the filesystem path of its
    pre-extracted previous-last-frame PNG (required for any segment with
    `background='previous_last_frame'`). `forge_video` populates this via
    a pre-pass; tests can pass a synthetic dict.
    """
    frame_cache = frame_cache or {}
    out = project.output
    if not out.produce_video:
        raise ValueError(
            "build_ffmpeg_command called but output.produce_video is False",
        )

    width, height = _resolve_resolution(project, resolution_override)

    if output_path is None:
        if not out.folder:
            raise ValueError("output.folder is required to build a command")
        output_path = str(Path(out.folder) / f"{out.basename}.mp4")

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
        pre = ["-loop", "1", "-t", f"{dur_s:g}"] if seg.is_still() else []
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
            filter_parts.append(
                f"[{vidx}:a]aresample=48000,aformat=channel_layouts=stereo"
                f"[{a_base}]",
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
            bridge_color = joiner_inst.color()  # '#rrggbb' or '#000000'
            v_bridge = f"v_bridge{bridge_idx}"
            a_bridge = f"a_bridge{bridge_idx}"
            bridge_idx += 1
            # ffmpeg `color` source takes 0xRRGGBB hex; strip the '#'.
            filter_parts.append(
                f"color=c=0x{bridge_color.lstrip('#')}:s={width}x{height}:"
                f"d={d_s:g}:r={_FRAME_RATE}[{v_bridge}]",
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

    filter_complex = ";\n".join(filter_parts)

    output_args = [
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", str(out.crf()),
        "-pix_fmt", "yuv420p",
        "-r", str(_FRAME_RATE),
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
    ]

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


def forge_video(
    project: Project,
    layout: Layout,
    ffmpeg_exe: Optional[str] = None,
    output_path: Optional[str] = None,
    resolution_override: Optional[tuple[int, int]] = None,
    log_callback: Optional[Callable[[str], None]] = None,
) -> Path:
    """Run ffmpeg to produce the output MP4. Returns the output path.

    Handles the `previous_last_frame` pre-pass: before the main forge,
    the last frame of each relevant preceding segment is extracted to
    a temp directory, which is cleaned up on exit.

    Raises `RuntimeError` if ffmpeg exits non-zero.
    """
    exe = ffmpeg_exe or _resolve_ffmpeg_exe()

    temp_dir = Path(tempfile.mkdtemp(prefix="forgeassembler_"))
    try:
        frame_cache = _build_frame_cache(project, exe, temp_dir)

        cmd = build_ffmpeg_command(
            project, layout,
            output_path=output_path,
            resolution_override=resolution_override,
            frame_cache=frame_cache,
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
        for line in proc.stdout:
            if log_callback:
                log_callback(line.rstrip())
        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(
                f"ffmpeg exited with code {proc.returncode} "
                f"(see log for details).",
            )
        return out_path
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
