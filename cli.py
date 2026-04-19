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
import sys
from pathlib import Path

from forgeassembler_core import (
    APP_NAME,
    VERSION,
    Project,
    RESOLUTION_PIXELS,
    Segment,
    categorize_channels,
    detect_folder,
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


def cmd_version(_args: argparse.Namespace) -> int:
    print(f"{APP_NAME} {VERSION}")
    return 0


def cmd_list_joiners(_args: argparse.Namespace) -> int:
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


def cmd_detect(args: argparse.Namespace) -> int:
    folder = Path(args.folder)
    if not folder.is_dir():
        print(f"ERROR: not a directory: {folder}", file=sys.stderr)
        return 2
    clips = detect_folder(folder)
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
            print(f"  audio_estim: {', '.join(sorted(clip.audio_estim.keys()))}")
        if not clip.funscripts and not clip.audio_estim:
            print("  (no associated funscripts or audio)")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    path = Path(args.project)
    if not path.is_file():
        print(f"ERROR: project file not found: {path}", file=sys.stderr)
        return 2
    try:
        project = Project.load(path)
    except (json.JSONDecodeError, ValueError, KeyError) as exc:
        print(f"ERROR: could not parse project: {exc}", file=sys.stderr)
        return 1
    issues = validate(project)
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
    emit a starter project JSON with one segment per detected clip
    and 'none' joiners between every pair.
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

    items: list = []
    skipped: list[str] = []
    clip_count = 0
    for sub in subfolders:
        try:
            clips = detect_folder(sub)
        except NotADirectoryError:
            continue
        if not clips:
            skipped.append(sub.name)
            continue
        for clip in clips:
            if items:
                items.append(ProjectJoiner(
                    id=new_id("join"),
                    joiner_type="none",
                ))
            items.append(Segment(
                id=new_id("seg"),
                video=str(clip.video),
            ))
            clip_count += 1

    if not items:
        print(
            f"ERROR: no clips detected in any subfolder of {parent}",
            file=sys.stderr,
        )
        return 2

    project = Project(
        items=items,
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
    print(f"  {clip_count} segments from {len(subfolders) - len(skipped)} "
          f"subfolder(s); all joiners are 'none'")
    if skipped:
        preview = ", ".join(skipped[:5])
        tail = "..." if len(skipped) > 5 else ""
        print(f"  skipped {len(skipped)} subfolder(s) with no video: "
              f"{preview}{tail}")
    print(f"\nNext: edit joiners to taste, then:")
    print(f"  python cli.py validate {output_json}")
    print(f"  python cli.py forge {output_json}")
    return 0


def cmd_forge(args: argparse.Namespace) -> int:
    path = Path(args.project)
    if not path.is_file():
        print(f"ERROR: project file not found: {path}", file=sys.stderr)
        return 2
    if args.no_video and args.no_funscripts:
        print("ERROR: --no-video and --no-funscripts cannot both be set.",
              file=sys.stderr)
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
    issues = validate(project)
    errors = [i for i in issues if i.level == "error"]
    if errors:
        for e in errors:
            loc = f" [{e.item_id}]" if e.item_id else ""
            print(f"ERROR{loc}: {e.message}", file=sys.stderr)
        return 1

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
        print(f"Forging video at {out.resolution} → {out.folder}/{out.basename}.mp4")
        try:
            output = forge_video(
                project, layout,
                ffmpeg_exe=ffmpeg_exe,
                resolution_override=resolution_override,
                frame_rate_override=frame_rate_override,
                log_callback=lambda line: print(line, file=sys.stderr),
            )
            print(f"Wrote {output}")
        except RuntimeError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 3

    if out.produce_funscripts:
        print(
            "NOTE: funscript production is not yet wired into the CLI; "
            "expected in the next commit.",
            file=sys.stderr,
        )

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
    p_detect.set_defaults(func=cmd_detect)

    p_validate = sub.add_parser("validate", help="check a project without forging")
    p_validate.add_argument("project", help="path to project JSON")
    p_validate.set_defaults(func=cmd_validate)

    p_list = sub.add_parser("list-joiners", help="list available joiner types")
    p_list.set_defaults(func=cmd_list_joiners)

    return parser


def main(argv: list[str] | None = None) -> int:
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
