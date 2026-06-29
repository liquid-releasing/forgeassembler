#!/usr/bin/env python3
# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.
"""Package a folder of LOOSE FunscriptForge channel funscripts into a
current-format `.forge` bundle (manifest.ffmeta zip), for use as a
forgeassembler `.forge`-import fixture.

This is the companion to `make_forge_fixture.ps1` for the case where a finished
scene exists only as loose output files (`<stem>.funscript`,
`<stem>.<channel>.funscript`) rather than a live FunscriptForge working folder
that `cli.py export` can repackage. The channel data is genuine FSF output; we
just lay it into the same manifest schema FunscriptForge's exporter writes:

    manifest.ffmeta
    motion.funscript                         <- <stem>.funscript
    stations/tcode/<stem>.<axis>.funscript   <- surge/sway/twist/roll/pitch
    stations/estim3p/<stem>.<chan>.funscript <- everything else e-stim

Usage:
    python build_forge_from_loose.py <folder> <stem> [--out <path.forge>]

Deterministic: project_id is derived from the stem so re-runs are stable.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import zipfile
from pathlib import Path

AXES = {"surge", "sway", "twist", "roll", "pitch"}
AXIS_CODE = {"surge": "L1", "sway": "L2", "twist": "R2", "roll": "R0", "pitch": "R1"}


def _split_channel(name: str, stem: str) -> str | None:
    """`<stem>.alpha.funscript` -> 'alpha'; `<stem>.funscript` -> None (main)."""
    if not name.endswith(".funscript"):
        return None
    core = name[: -len(".funscript")]
    if core == stem:
        return None
    prefix = stem + "."
    if core.startswith(prefix):
        return core[len(prefix):]
    return None


def _duration_ms(motion: Path) -> int:
    try:
        data = json.loads(motion.read_text(encoding="utf-8"))
        actions = data.get("actions") or []
        return int(actions[-1]["at"]) if actions else 0
    except (OSError, ValueError, KeyError, IndexError):
        return 0


def build(folder: Path, stem: str, out: Path,
          media_file: Path | None = None, display_name: str | None = None) -> dict:
    motion = folder / f"{stem}.funscript"
    if not motion.is_file():
        raise SystemExit(f"ERROR: motion funscript not found: {motion}")

    # Collect loose channel funscripts that share the stem.
    channels: dict[str, Path] = {}
    for f in sorted(folder.glob(f"{stem}.*.funscript")):
        ch = _split_channel(f.name, stem)
        if ch:
            channels[ch] = f

    artifacts = [{"path": "motion.funscript", "kind": "funscript", "role": "stroke", "axis": "L0"}]
    staged: list[tuple[str, Path]] = [("motion.funscript", motion)]
    stations: dict[str, dict] = {}
    for ch, path in channels.items():
        if ch in AXES:
            group = "tcode"
            rel = f"stations/{group}/{stem}.{ch}.funscript"
            artifacts.append({"path": rel, "kind": "funscript", "role": "stroke", "axis": AXIS_CODE[ch]})
        else:
            group = "estim3p"
            rel = f"stations/{group}/{stem}.{ch}.funscript"
            artifacts.append({"path": rel, "kind": "funscript", "role": "estim"})
        staged.append((rel, path))
        stations.setdefault(group, {"files": []})["files"].append(f"{stem}.{ch}.funscript")

    # Display name (the segment's title); the funscript-finding stem stays put.
    bundle_stem = display_name or stem
    # Project id keys the import cache — vary it by display name so distinct
    # bundles built from the same channels don't collide in the cache.
    manifest = {
        "version": 1, "schema": "ffmeta/v1", "stem": bundle_stem,
        "created_with": "FunscriptForge", "duration_ms": _duration_ms(motion),
        "project_id": hashlib.md5(bundle_stem.encode("utf-8")).hexdigest(),
        "project_version": 1,
        "exported_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "artifacts": artifacts, "stations": stations,
        "repackaged_from_loose": True,
    }
    # Media relink key: when the bundle sits next to a file of this name+size,
    # the importer auto-resolves the video — no relink dialog.
    if media_file is not None:
        mf = Path(media_file)
        if mf.is_file():
            manifest["media"] = {
                "filename": mf.name, "size": mf.stat().st_size, "bundled": False,
            }

    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.ffmeta", json.dumps(manifest, indent=2))
        for rel, src in staged:
            z.write(src, rel)
    return manifest


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("folder", help="Folder holding <stem>.funscript + <stem>.<channel>.funscript")
    ap.add_argument("stem", help="Scene stem (e.g. VictoriaOaks_stingy)")
    ap.add_argument("--out", default=None, help="Output .forge path")
    ap.add_argument("--media-file", default=None,
                    help="Local video the bundle should auto-relink to (writes a media block keyed on name+size)")
    ap.add_argument("--display-name", default=None,
                    help="Segment title in the manifest (default: stem)")
    args = ap.parse_args(argv)

    folder = Path(args.folder).resolve()
    out = Path(args.out) if args.out else (
        Path(r"C:\Users\bruce\Projects\_lqr\forgeassembler\test_media\forge_bundles")
        / f"{args.stem}.full.forge"
    )
    manifest = build(folder, args.stem, out,
                     media_file=args.media_file, display_name=args.display_name)
    print(json.dumps({
        "path": str(out),
        "channels": [a["path"] for a in manifest["artifacts"]],
        "duration_ms": manifest["duration_ms"],
        "stations": {k: v["files"] for k, v in manifest["stations"].items()},
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
