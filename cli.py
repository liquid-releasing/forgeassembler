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
    categorize_channels,
    detect_folder,
    joiner_specs,
    validate,
)


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


def cmd_forge(args: argparse.Namespace) -> int:
    # Phase 1 scaffold — actual ffmpeg forge is not implemented yet.
    # We validate the project, then report what WOULD happen.
    path = Path(args.project)
    if not path.is_file():
        print(f"ERROR: project file not found: {path}", file=sys.stderr)
        return 2
    project = Project.load(path)
    if args.output:
        project.output_folder = args.output
    if args.basename:
        project.output_basename = args.basename
    issues = validate(project)
    errors = [i for i in issues if i.level == "error"]
    if errors:
        for e in errors:
            loc = f" [{e.item_id}]" if e.item_id else ""
            print(f"ERROR{loc}: {e.message}", file=sys.stderr)
        return 1

    segs = project.segments()
    joins = project.joiners()
    print(f"[dry-run] Project OK — {len(segs)} segments, {len(joins)} joiners.")
    print(f"[dry-run] Output folder: {project.output_folder or '(not set)'}")
    print(f"[dry-run] Output basename: {project.output_basename}")
    print(f"[dry-run] Channels selected: {', '.join(project.output_channels.selected()) or '(none)'}")
    print("[dry-run] Video forging is not implemented yet — run in the UI or wait for v0.0.1.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="forgeassembler", description=f"{APP_NAME} CLI")
    parser.add_argument("--version", action="store_true", help="print version and exit")
    sub = parser.add_subparsers(dest="command")

    p_forge = sub.add_parser("forge", help="run a saved project")
    p_forge.add_argument("project", help="path to project JSON")
    p_forge.add_argument("--output", help="override output folder")
    p_forge.add_argument("--basename", help="override output basename")
    p_forge.set_defaults(func=cmd_forge)

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
