#!/usr/bin/env python3
# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""ForgeAssembler CLI.

Usage:
  forgeassembler forge <project.json> [--output DIR] [--basename NAME]
  forgeassembler detect <folder>
  forgeassembler validate <project.json>
  forgeassembler list-joiners
  forgeassembler --version

Exit codes:
  0  success
  1  validation error
  2  resolution error (missing file, corrupt video)
  3  ffmpeg error
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from forgeassembler_core import (
    APP_NAME,
    VERSION,
    Project,
    RESOLUTION_PIXELS,
    Section,
    Segment,
    categorize_channels,
    detect_folder,
    forge_bundles_in,
    forge_funscripts,
    forge_video,
    joiner_specs,
    new_id,
    validate,
)
from forgeassembler_core.project import Joiner as ProjectJoiner
from forgeassembler_core.project import Output
from forgeassembler_core.concat_video import _resolve_ffmpeg_exe
from forgeassembler_core.layout import lay_out
from forgeassembler_core.probe import probe_duration_ms


# ── Helpers shared by the JSON-emitting subcommands (Tauri bridge) ─────
def _clip_to_dict(clip) -> dict:
    """Serialize a DetectedClip for `detect --format json`. Paths become
    absolute strings; channels keep their key→path mapping plus the
    grouped view the UI renders."""
    return {
        "video": str(clip.video),
        "stem": clip.stem,
        "funscripts": {k: str(v) for k, v in clip.funscripts.items()},
        "audio_estim": {k: str(v) for k, v in clip.audio_estim.items()},
        "channel_groups": {
            g: sorted(chs)
            for g, chs in categorize_channels(clip.funscripts).items()
            if chs
        },
    }


def _progress_writer():
    """Return a callback that appends progress lines to the file named by
    FORGEASSEMBLER_PROGRESS_FILE (the Tauri shell tails it and re-emits each
    line as an `fa:progress` event) AND mirrors them to stderr. When the env
    var is unset (plain CLI use) it just writes stderr."""
    path = os.environ.get("FORGEASSEMBLER_PROGRESS_FILE")

    def emit(line: str) -> None:
        print(line, file=sys.stderr)
        if path:
            try:
                with open(path, "a", encoding="utf-8") as fh:
                    fh.write(line.rstrip("\n") + "\n")
            except OSError:
                pass

    return emit


def _force_utf8_streams() -> None:
    """Print UTF-8 whatever console the CLI inherits.

    Windows hands a spawned process a cp1252 stdout, which raises
    UnicodeEncodeError on any character outside Latin-1 — the "→" in
    the forge log killed a real run. The Tauri shell decodes our stdout
    as UTF-8 regardless, so force it on both streams and never die on a
    glyph.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def cmd_version(_args: argparse.Namespace) -> int:
    print(f"{APP_NAME} {VERSION}")
    return 0


def cmd_list_joiners(args: argparse.Namespace) -> int:
    if getattr(args, "format", "text") == "json":
        payload = {
            "joiners": [
                {
                    "joiner_type": spec.joiner_type,
                    "display_name": spec.display_name,
                    "description": spec.description,
                    "params_schema": spec.params_schema,
                }
                for spec in joiner_specs()
            ]
        }
        print(json.dumps(payload))
        return 0
    for spec in joiner_specs():
        print(f"{spec.joiner_type}")
        print(f"  name: {spec.display_name}")
        print(f"  description: {spec.description}")
        if spec.params_schema:
            print("  params:")
            for name, info in spec.params_schema.items():
                default = info.get("default")
                typ = info.get("type", "?")
                label = info.get("label", name)
                print(f"    {name}  ({typ}, default={default!r}) — {label}")
        print()
    return 0


# Rough encode throughput, in seconds of OUTPUT per second of wall clock,
# at 1080p. Measured on this project's own runs (13:14 of 1080p in about a
# minute on NVENC ~ 13x) and deliberately conservative. The Forge tab used
# to hardcode 0.5x -- a CPU-ish guess -- and told a GPU machine 27 minutes
# for a 2-minute job.
_ENCODE_RATE_1080P = {
    "nvenc": 11.0,
    "qsv": 8.0,
    "amf": 8.0,
    "libx264": 0.8,
}
# Pixel cost relative to 1080p. 4K is 4x the pixels and encodes roughly
# that much slower.
_RESOLUTION_COST = {
    "1080p": 1.0, "1440p": 1.8, "4k": 4.0,
    "uw_1080p": 1.35, "uw_1440p": 2.4,
    "4_3_hd": 0.75, "3_4_hd": 0.75, "9_16_hd": 1.0,
    "source": 1.0,
}


def cmd_encoder(args: argparse.Namespace) -> int:
    """Report the encoder THIS machine will actually use, and how fast it
    is, so the UI can estimate forge time instead of guessing."""
    from forgeassembler_core.concat_video import resolve_video_encoder
    try:
        exe = _resolve_ffmpeg_exe()
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3
    encoder = resolve_video_encoder(exe)
    hardware = encoder != "libx264"
    payload = {
        "encoder": encoder,
        "hardware": hardware,
        "label": {"nvenc": "NVIDIA NVENC", "qsv": "Intel Quick Sync",
                  "amf": "AMD AMF"}.get(encoder, "CPU (libx264)"),
        # seconds of output encoded per second of wall clock, at 1080p
        "rate_1080p": _ENCODE_RATE_1080P.get(encoder, 0.8),
        "resolution_cost": _RESOLUTION_COST,
    }
    if getattr(args, "format", "text") == "json":
        print(json.dumps(payload))
        return 0
    print(f"{payload['label']}  ({encoder}, "
          f"{'hardware' if hardware else 'software'})")
    return 0


def cmd_detect_forge(args: argparse.Namespace) -> int:
    """List the `.forge` bundles in a folder, without opening any of them.

    Backs the Build tab's "Add folder", which adds one SECTION per scene
    (a section is what becomes a chapter). Shallow and cheap on purpose —
    the UI imports each bundle separately so it can report progress and
    keep going when one needs its video relinked.
    """
    folder = Path(args.folder)
    try:
        bundles = forge_bundles_in(folder)
    except NotADirectoryError:
        print(f"ERROR: not a directory: {folder}", file=sys.stderr)
        return 2
    payload = {
        "folder": str(folder),
        "bundles": [{"path": str(b), "stem": b.stem} for b in bundles],
    }
    if getattr(args, "format", "text") == "json":
        print(json.dumps(payload))
        return 0
    if not bundles:
        print(f"No .forge scenes found in {folder}.")
        return 0
    for b in bundles:
        print(b.name)
    return 0


def cmd_detect(args: argparse.Namespace) -> int:
    folder = Path(args.folder)
    if not folder.is_dir():
        print(f"ERROR: not a directory: {folder}", file=sys.stderr)
        return 2
    clips = detect_folder(folder)
    if getattr(args, "format", "text") == "json":
        print(json.dumps({"clips": [_clip_to_dict(c) for c in clips]}))
        return 0
    if not clips:
        print(f"No video files found in {folder}.")
        return 0
    for clip in clips:
        print(f"{clip.stem}  [{clip.video.name}]")
        if clip.funscripts:
            groups = categorize_channels(clip.funscripts)
            for group, channels in groups.items():
                if channels:
                    print(f"  {group}: {', '.join(sorted(channels))}")
        if clip.audio_estim:
            # Strip .wav for compactness; matches the UI segment-card
            # caption format ("Audio (estim): stereostim, legacy, ...").
            pretty = sorted(
                k.replace(".wav", "") for k in clip.audio_estim
            )
            print(f"  audio (estim): {', '.join(pretty)}")
        if not clip.funscripts and not clip.audio_estim:
            print("  (no associated funscripts or audio)")
    return 0


def cmd_import_forge(args: argparse.Namespace) -> int:
    """Import a FunscriptForge `.forge` bundle as a single Segment.

    Unpacks the bundle, maps its manifest channels, and (when a video can be
    relinked — either bundled media or `--video`) emits the Segment dict the UI
    appends. When no video is resolvable, emits the channel map + `needs_video`
    so the caller can prompt for relink.
    """
    from forgeassembler_core import detect_forge_bundle, forge_bundle_to_segment, is_forge_bundle

    bundle_path = Path(args.bundle)
    if not is_forge_bundle(bundle_path):
        print(f"ERROR: not a .forge bundle (expected a .forge zip): {bundle_path}",
              file=sys.stderr)
        return 2
    try:
        bundle = detect_forge_bundle(
            bundle_path,
            cache_root=args.cache_root,
            media_roots=[args.media_root] if args.media_root else None,
        )
    except (ValueError, OSError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    video = args.video or (str(bundle.media_path) if bundle.media_path else None)
    groups = categorize_channels({ch: p for ch, p in bundle.funscripts.items()})
    payload = {
        "stem": bundle.stem,
        "project_id": bundle.project_id,
        "project_version": bundle.project_version,
        "duration_ms": bundle.duration_ms,
        "channels": bundle.channels,
        "channel_groups": {g: sorted(chs) for g, chs in groups.items() if chs},
        "media_resolved": video is not None,
        "video": video,
        "cache_dir": str(bundle.cache_dir),
        # Haptic audio the bundle carries, keyed by engine channel.
        "audio_estim": {ch: str(p) for ch, p in bundle.audio_estim.items()},
        # Analysis the preview can load instead of re-deriving: waveform
        # peaks, beats, chapters, phrases, characters.
        "sidecars": {name: str(p) for name, p in bundle.sidecars.items()},
        # hero / funscript / audio / spectrogram / chapter_N stills.
        "thumbnails": {role: str(p) for role, p in bundle.thumbnails.items()},
    }
    if video:
        seg = forge_bundle_to_segment(bundle, video=video)
        payload["segment"] = seg.to_dict()
        payload["needs_video"] = False
    else:
        payload["segment"] = None
        payload["needs_video"] = True

    if getattr(args, "format", "text") == "json":
        print(json.dumps(payload))
        return 0
    print(f"{bundle.stem}  ({len(bundle.channels)} channel(s), "
          f"{(bundle.duration_ms or 0) // 1000}s)")
    for group, chans in payload["channel_groups"].items():
        print(f"  {group}: {', '.join(chans)}")
    if video:
        print(f"  video: {video}")
    else:
        print("  video: (unresolved — pass --video to relink)")
    return 0


# Reference speed for normalising the preview strip: 500 pos-units/sec is
# already "hot" on the OpenFunscripter/XBVR gradient the render path uses,
# so anything at or above it pins the bin to 1.0.
PREVIEW_HOT_SPEED = 500.0


def cmd_preview(args: argparse.Namespace) -> int:
    """Summarise the COMBINED funscript without rendering anything.

    Runs the same layout + concat the forge does, so the strip in the Build
    tab describes the file the user would actually get — a preview computed
    a second way would drift from the output and quietly lie.

    Emits per-bin peak speed (normalised 0-1) plus honest totals. Bins carry
    the segment and section they fall in so the UI can colour them; naming
    the section rather than a colour keeps display choices out of here.
    """
    from forgeassembler_core.concat_funscript import (
        _build_parts_for_channel, concat_funscripts,
    )
    from forgeassembler_core.heatmap import compute_peak_speeds
    from forgeassembler_core.project import Segment as _Seg

    try:
        project = Project.load(args.project)
    except (OSError, ValueError, KeyError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    try:
        ffmpeg_exe = _resolve_ffmpeg_exe()
        layout = lay_out(project, probe=lambda p: probe_duration_ms(p, ffmpeg_exe))
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    total_ms = layout.total_duration_ms
    combined = concat_funscripts(_build_parts_for_channel(project, layout, args.channel))
    actions = combined.get("actions", [])

    bin_count = max(1, min(args.bins, max(1, total_ms // 250) if total_ms else args.bins))
    speeds = compute_peak_speeds(actions, bin_count, total_ms)

    # Which segment/section owns each bin — walk the layout once.
    bin_ms = (total_ms / bin_count) if bin_count else 0
    owner: list[tuple[str | None, str | None]] = [(None, None)] * bin_count
    section_of: dict[str, str] = {
        seg.id: sec.id for sec in project.sections for seg in sec.segments
    }
    for li in layout.items:
        if not isinstance(li.item, _Seg) or not bin_ms:
            continue
        first = max(0, int(li.start_ms / bin_ms))
        last = min(bin_count - 1, int(max(li.start_ms, li.end_ms - 1) / bin_ms))
        for b in range(first, last + 1):
            owner[b] = (li.item.id, section_of.get(li.item.id))

    # Stroke rate from direction reversals: two reversals make one cycle.
    reversals = 0
    if len(actions) > 2:
        prev_dir = 0
        for a, b in zip(actions[:-1], actions[1:]):
            d = (b["pos"] > a["pos"]) - (b["pos"] < a["pos"])
            if d and prev_dir and d != prev_dir:
                reversals += 1
            if d:
                prev_dir = d
    # The stroke line itself, thinned to something a strip can draw. Peak-
    # preserving: each bucket keeps its highest and lowest action, so the
    # envelope survives and a fast passage cannot thin down to a flat line
    # the way a plain every-Nth stride would make it.
    points: list[list[int]] = []
    if actions:
        if len(actions) <= args.max_points:
            points = [[int(a["at"]), int(a["pos"])] for a in actions]
        else:
            buckets = max(1, args.max_points // 2)
            width = max(1, (total_ms or 1) / buckets)
            by_bucket: dict[int, list[dict]] = {}
            for a in actions:
                by_bucket.setdefault(int(int(a["at"]) / width), []).append(a)
            for _b, group in sorted(by_bucket.items()):
                lo = min(group, key=lambda a: int(a["pos"]))
                hi = max(group, key=lambda a: int(a["pos"]))
                for a in sorted({id(lo): lo, id(hi): hi}.values(),
                                key=lambda a: int(a["at"])):
                    points.append([int(a["at"]), int(a["pos"])])

    minutes = total_ms / 60000.0
    payload = {
        "points": points,
        "channel": args.channel,
        "duration_ms": total_ms,
        "action_count": len(actions),
        "avg_bpm": round((reversals / 2.0) / minutes, 1) if minutes > 0 else 0.0,
        "peak_speed": round(max(speeds), 1) if speeds else 0.0,
        "peak_velocity": round(min(1.0, (max(speeds) if speeds else 0.0) / PREVIEW_HOT_SPEED), 3),
        "bins": [
            {"speed": round(sp, 1),
             "v": round(min(1.0, sp / PREVIEW_HOT_SPEED), 3),
             "seg_id": owner[i][0], "section_id": owner[i][1]}
            for i, sp in enumerate(speeds)
        ],
    }
    if getattr(args, "format", "json") == "json":
        print(json.dumps(payload))
        return 0
    print(f"{args.channel}: {payload['action_count']} actions over "
          f"{total_ms // 1000}s, {payload['avg_bpm']} bpm, "
          f"peak {payload['peak_speed']} units/s")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    path = Path(args.project)
    as_json = getattr(args, "format", "text") == "json"
    if not path.is_file():
        if as_json:
            print(json.dumps({
                "ok": False,
                "errors": [{"level": "error",
                            "message": f"project file not found: {path}",
                            "item_id": None}],
                "warnings": [],
            }))
            return 2
        print(f"ERROR: project file not found: {path}", file=sys.stderr)
        return 2
    try:
        project = Project.load(path)
    except (json.JSONDecodeError, ValueError, KeyError) as exc:
        if as_json:
            print(json.dumps({
                "ok": False,
                "errors": [{"level": "error",
                            "message": f"could not parse project: {exc}",
                            "item_id": None}],
                "warnings": [],
            }))
            return 1
        print(f"ERROR: could not parse project: {exc}", file=sys.stderr)
        return 1
    issues = validate(project)
    if as_json:
        errors = [i for i in issues if i.level == "error"]
        warnings = [i for i in issues if i.level == "warning"]
        print(json.dumps({
            "ok": not errors,
            "errors": [{"level": i.level, "message": i.message,
                        "item_id": i.item_id} for i in errors],
            "warnings": [{"level": i.level, "message": i.message,
                          "item_id": i.item_id} for i in warnings],
            "segment_count": len(project.segments()),
            "joiner_count": len(project.joiners()),
        }))
        return 1 if errors else 0
    if not issues:
        print(f"OK — project has {len(project.segments())} segment(s), "
              f"{len(project.joiners())} joiner(s).")
        return 0
    errors = [i for i in issues if i.level == "error"]
    warnings = [i for i in issues if i.level == "warning"]
    for w in warnings:
        loc = f" [{w.item_id}]" if w.item_id else ""
        print(f"WARNING{loc}: {w.message}", file=sys.stderr)
    for e in errors:
        loc = f" [{e.item_id}]" if e.item_id else ""
        print(f"ERROR{loc}: {e.message}", file=sys.stderr)
    return 1 if errors else 0


def cmd_probe(args: argparse.Namespace) -> int:
    """Print a media file's duration in milliseconds (one integer to stdout)."""
    path = Path(args.video)
    if not path.is_file():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 2
    try:
        ffmpeg_exe = _resolve_ffmpeg_exe()
        ms = probe_duration_ms(path, ffmpeg_exe)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3
    print(int(ms))
    return 0


def cmd_thumbnail(args: argparse.Namespace) -> int:
    """Extract a single frame at `--at <ms>` to `--out <png>`."""
    video = Path(args.video)
    if not video.is_file():
        print(f"ERROR: file not found: {video}", file=sys.stderr)
        return 2
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        ffmpeg_exe = _resolve_ffmpeg_exe()
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3
    seconds = max(0.0, args.at / 1000.0)
    result = subprocess.run(
        [
            ffmpeg_exe, "-hide_banner", "-loglevel", "error",
            "-ss", f"{seconds:.3f}", "-i", str(video),
            "-frames:v", "1", "-vf", "scale=320:-2:flags=lanczos", "-update", "1",
            "-y", str(out),
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        print(f"ERROR: ffmpeg thumbnail failed: {result.stderr}", file=sys.stderr)
        return 3
    print(str(out))
    return 0


def _natural_key(path: Path) -> tuple:
    """Sort `0, 1, 2, ..., 10, 11, ...` instead of lexicographic
    `0, 1, 10, 11, ..., 2, 3, ...`.
    """
    try:
        return (0, int(path.name))
    except ValueError:
        return (1, path.name)


def cmd_new_project(args: argparse.Namespace) -> int:
    """Scan subfolders of a parent, call detect_folder on each, and
    emit a starter project JSON.

    v2.0 layout: all detected clips land in ONE Section (cut-joined).
    The user can split it later in the UI by picking a clip and
    saying "Split section here" — that boundary becomes its own new
    section with whatever transition the user chooses.
    """
    parent = Path(args.folder)
    if not parent.is_dir():
        print(f"ERROR: not a directory: {parent}", file=sys.stderr)
        return 2

    subfolders = sorted(
        (p for p in parent.iterdir() if p.is_dir()),
        key=_natural_key,
    )
    if not subfolders:
        print(
            f"ERROR: no subfolders found under {parent}",
            file=sys.stderr,
        )
        return 2

    segments: list[Segment] = []
    skipped: list[str] = []
    for sub in subfolders:
        try:
            clips = detect_folder(sub)
        except NotADirectoryError:
            continue
        if not clips:
            skipped.append(sub.name)
            continue
        for clip in clips:
            segments.append(Segment(
                id=new_id("seg"),
                video=str(clip.video),
            ))

    if not segments:
        print(
            f"ERROR: no clips detected in any subfolder of {parent}",
            file=sys.stderr,
        )
        return 2

    section = Section(id=new_id("sec"), segments=segments)
    project = Project(
        sections=[section],
        output=Output(
            folder=args.output_folder or str(parent.parent / "out"),
            basename=args.basename or parent.parent.name or parent.name,
            resolution=args.resolution,
        ),
    )

    output_json = Path(args.output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    project.save(output_json)

    print(f"Wrote {output_json}")
    print(f"  1 section with {len(segments)} clip(s) from "
          f"{len(subfolders) - len(skipped)} subfolder(s); "
          f"all clips cut together")
    if skipped:
        preview = ", ".join(skipped[:5])
        tail = "..." if len(skipped) > 5 else ""
        print(f"  skipped {len(skipped)} subfolder(s) with no video: "
              f"{preview}{tail}")
    print(f"\nNext: split / tune sections in the UI, then:")
    print(f"  python cli.py validate {output_json}")
    print(f"  python cli.py forge {output_json}")
    return 0


def cmd_forge(args: argparse.Namespace) -> int:
    path = Path(args.project)
    if not path.is_file():
        print(f"ERROR: project file not found: {path}", file=sys.stderr)
        return 2
    if (
        args.no_video and args.no_funscripts and args.no_audio_estim
    ):
        print(
            "ERROR: --no-video / --no-funscripts / --no-audio-estim "
            "cannot all be set.",
            file=sys.stderr,
        )
        return 1
    project = Project.load(path)
    if args.output:
        project.output.folder = args.output
    if args.basename:
        project.output.basename = args.basename
    if args.no_video:
        project.output.produce_video = False
    if args.no_funscripts:
        project.output.produce_funscripts = False
    if args.no_audio_estim:
        project.output.produce_audio_estim = False
    issues = validate(project)
    errors = [i for i in issues if i.level == "error"]
    if errors:
        for e in errors:
            loc = f" [{e.item_id}]" if e.item_id else ""
            print(f"ERROR{loc}: {e.message}", file=sys.stderr)
        return 1

    # JSON mode: human chatter goes to stderr (via `say`), stdout carries only
    # the final summary object. `emit` mirrors progress to the Tauri progress
    # file. Text mode keeps the legacy human stdout output.
    as_json = getattr(args, "format", "text") == "json"
    emit = _progress_writer()
    say = (lambda m: print(m, file=sys.stderr)) if as_json else print
    summary: dict = {"video": None, "funscripts": [], "audio_estim": []}

    out = project.output

    # Resolve ffmpeg + build layout (probes duration via ffmpeg for real
    # videos; stills use their declared still_duration_s).
    try:
        ffmpeg_exe = _resolve_ffmpeg_exe()
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3

    def _probe(p: Path) -> int:
        return probe_duration_ms(p, ffmpeg_exe)

    try:
        layout = lay_out(project, probe=_probe)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    # Tell the UI how long the finished video will be, so it can turn
    # ffmpeg's `time=` reports into a real percentage, and how many stages
    # are coming, so it doesn't have to guess our stage count from its own
    # copy of the project. `meta:` lines carry data, not stage text — the
    # footer shows `progress:` lines only.
    stage_total = sum((
        bool(out.produce_video),
        bool(out.produce_funscripts),
        bool(out.produce_audio_estim),
    ))
    emit(f"meta: duration_ms={layout.total_duration_ms} stages={stage_total}")

    # Resolve "source" resolution by probing the first video segment.
    resolution_override = None
    if out.produce_video and out.resolution == "source":
        first_video_seg = next(
            (s for s in project.segments() if not s.is_still()),
            None,
        )
        if first_video_seg is None:
            print(
                "ERROR: output.resolution='source' but project has no "
                "video segments to probe.",
                file=sys.stderr,
            )
            return 1
        # Probe first segment for actual pixel dims via ffmpeg -i output.
        # For simplicity in v1 we default to 1080p here; the proper
        # ffprobe-based resolution detection lands alongside a later feature.
        print(
            "WARNING: output.resolution='source' probing not yet "
            "implemented; falling back to 1920x1080.",
            file=sys.stderr,
        )
        resolution_override = (1920, 1080)

    # When frame_rate is 'source', probe first video segment for a fps.
    # forge_video does this internally; we probe here too so we can print
    # what got chosen (otherwise the user has no feedback until ffmpeg
    # starts logging).
    from forgeassembler_core.concat_video import _resolve_source_frame_rate
    frame_rate_override = None
    if out.produce_video:
        try:
            frame_rate_override = _resolve_source_frame_rate(project, ffmpeg_exe)
        except RuntimeError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2
        if frame_rate_override is not None:
            print(
                f"Frame rate: matched source → {frame_rate_override} fps",
                file=sys.stderr,
            )

    if out.produce_video:
        from forgeassembler_core.concat_video import resolve_video_encoder
        _enc = resolve_video_encoder(ffmpeg_exe)
        _enc_label = {
            "nvenc": "GPU · NVIDIA NVENC",
            "qsv":   "GPU · Intel Quick Sync",
            "amf":   "GPU · AMD AMF",
        }.get(_enc, "CPU · libx264")
        emit(f"progress: forging video at {out.resolution} ({_enc_label})")
        say(f"Forging video at {out.resolution} [{_enc_label}] → {out.folder}/{out.basename}.mp4")
        try:
            output = forge_video(
                project, layout,
                ffmpeg_exe=ffmpeg_exe,
                resolution_override=resolution_override,
                frame_rate_override=frame_rate_override,
                log_callback=emit,
            )
            summary["video"] = str(output)
            say(f"Wrote {output}")
        except RuntimeError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 3

    if out.produce_funscripts:
        emit("progress: forging funscripts")
        try:
            written = forge_funscripts(project, layout)
        except Exception as e:  # noqa: BLE001
            print(f"ERROR: funscript forge failed: {e}", file=sys.stderr)
            return 3
        if written:
            summary["funscripts"] = [str(p) for p in written]
            say(f"Wrote {len(written)} funscript file(s):")
            for path in written:
                say(f"  {path}")
        else:
            say("No funscripts written (no selected channel had any "
                "actions across the project).")

    if out.produce_audio_estim:
        emit("progress: forging haptic-estim audio")
        from forgeassembler_core.concat_audio_estim import forge_audio_estim
        try:
            written_audio = forge_audio_estim(
                project, layout, ffmpeg_exe=ffmpeg_exe,
            )
        except Exception as e:  # noqa: BLE001
            print(
                f"ERROR: audio-estim concat failed: {e}",
                file=sys.stderr,
            )
            return 3
        if written_audio:
            summary["audio_estim"] = [str(p) for p in written_audio]
            say(f"Wrote {len(written_audio)} estim audio file(s):")
            for path in written_audio:
                say(f"  {path}")
        else:
            say("No estim audio written (no segment had a "
                ".stereostim.wav / .legacy.wav / .prostate.stereostim.wav "
                "sibling).")

    emit("progress: done")
    if as_json:
        print(json.dumps(summary))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="forgeassembler", description=f"{APP_NAME} CLI")
    parser.add_argument("--version", action="store_true", help="print version and exit")
    sub = parser.add_subparsers(dest="command")

    p_forge = sub.add_parser("forge", help="run a saved project")
    p_forge.add_argument("project", help="path to project JSON")
    p_forge.add_argument("--output", help="override output folder")
    p_forge.add_argument("--basename", help="override output basename")
    p_forge.add_argument("--no-video", action="store_true",
                         help="skip the video pipeline (funscripts only)")
    p_forge.add_argument("--no-funscripts", action="store_true",
                         help="skip the funscript pipeline (video only)")
    p_forge.add_argument(
        "--no-audio-estim", action="store_true",
        help=(
            "skip the haptic-estim audio pipeline (don't emit per-channel "
            ".stereostim.wav / .legacy.wav / .prostate.stereostim.wav)"
        ),
    )
    p_forge.add_argument("--format", choices=("text", "json"), default="text",
                         help="json: stream progress to stderr, print a summary object to stdout")
    p_forge.set_defaults(func=cmd_forge)

    p_new = sub.add_parser(
        "new-project",
        help="scan subfolders and emit a starter project JSON "
             "(one segment per subfolder, 'none' joiners between)",
    )
    p_new.add_argument("folder", help="parent folder to scan")
    p_new.add_argument("output_json", help="path to write the project JSON")
    p_new.add_argument("--output-folder",
                       help="where the forged output will land")
    p_new.add_argument("--basename",
                       help="output basename (default: parent folder name)")
    p_new.add_argument("--resolution", default="1080p",
                       help="output resolution key (default: 1080p)")
    p_new.set_defaults(func=cmd_new_project)

    p_detect = sub.add_parser("detect", help="show what auto-detects in a folder")
    p_detect.add_argument("folder", help="folder to scan")
    p_detect.add_argument("--format", choices=("text", "json"), default="text",
                          help="json: emit a {clips:[...]} object for the UI")
    p_detect.set_defaults(func=cmd_detect)

    p_encoder = sub.add_parser(
        "encoder", help="report the video encoder this machine will use")
    p_encoder.add_argument("--format", choices=("text", "json"), default="text",
                           help="json: emit encoder + throughput for the UI")
    p_encoder.set_defaults(func=cmd_encoder)

    p_detect_forge = sub.add_parser(
        "detect-forge", help="list the .forge scenes in a folder")
    p_detect_forge.add_argument("folder", help="folder to scan")
    p_detect_forge.add_argument("--format", choices=("text", "json"), default="text",
                                help="json: emit a {bundles:[...]} object for the UI")
    p_detect_forge.set_defaults(func=cmd_detect_forge)

    p_import = sub.add_parser(
        "import-forge",
        help="import a FunscriptForge .forge bundle as one Segment",
    )
    p_import.add_argument("bundle", help="path to a .forge bundle (zip)")
    p_import.add_argument("--video", help="relink the source video for the segment")
    p_import.add_argument("--media-root", help="extra folder to search for the source video")
    p_import.add_argument("--cache-root", help="where to extract bundles (default: temp)")
    p_import.add_argument("--format", choices=("text", "json"), default="text",
                          help="json: emit the segment + channel map for the UI")
    p_import.set_defaults(func=cmd_import_forge)

    p_preview = sub.add_parser(
        "preview",
        help="summarise the combined funscript (no render) for the live strip",
    )
    p_preview.add_argument("project", help="path to project JSON")
    p_preview.add_argument("--channel", default="main",
                           help="which channel to summarise (default: main)")
    p_preview.add_argument("--bins", type=int, default=600,
                           help="how many time buckets to report (default: 600)")
    p_preview.add_argument("--max-points", type=int, default=2000,
                           help="cap on returned [at, pos] pairs (default: 2000)")
    p_preview.add_argument("--format", choices=("text", "json"), default="json")
    p_preview.set_defaults(func=cmd_preview)

    p_validate = sub.add_parser("validate", help="check a project without forging")
    p_validate.add_argument("project", help="path to project JSON")
    p_validate.add_argument("--format", choices=("text", "json"), default="text",
                            help="json: emit an {ok, errors, warnings} object")
    p_validate.set_defaults(func=cmd_validate)

    p_list = sub.add_parser("list-joiners", help="list available joiner types")
    p_list.add_argument("--format", choices=("text", "json"), default="text",
                        help="json: emit a {joiners:[...]} object")
    p_list.set_defaults(func=cmd_list_joiners)

    p_probe = sub.add_parser("probe", help="print a media file's duration in ms")
    p_probe.add_argument("video", help="path to a video/audio file")
    p_probe.set_defaults(func=cmd_probe)

    p_thumb = sub.add_parser("thumbnail", help="extract one frame to a PNG")
    p_thumb.add_argument("video", help="path to a video file")
    p_thumb.add_argument("--at", type=int, default=0, help="timestamp in ms (default 0)")
    p_thumb.add_argument("--out", required=True, help="output PNG path")
    p_thumb.set_defaults(func=cmd_thumbnail)

    return parser


def main(argv: list[str] | None = None) -> int:
    _force_utf8_streams()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        return cmd_version(args)
    if not args.command:
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
