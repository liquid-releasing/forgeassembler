#!/usr/bin/env python3
"""Write a tiny two-clip project for CI to forge through the FROZEN binary.

The release workflow runs `forge-cli forge` on this before it packages the
app. That matters because a PyInstaller freeze fails at RUNTIME, not at build
time, and it fails in places a `--version` check never reaches: matplotlib's
mpl-data (the heatmap), Pillow's plugins, the joiner registry resolving a
plugin by name, and imageio-ffmpeg's bundled binary.

FunscriptForge shipped a build whose `yaml` module was simply absent, because
its one smoke command never touched YAML. This is the cheap version of not
doing that again.

Usage:  python scripts/ci_smoke_project.py <dir>

Writes `<dir>/smoke.forgeproject.json` plus the clips it references, using the
`t.mp4` that the workflow has already made with the bundled ffmpeg.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    root = Path(sys.argv[1]).resolve()
    root.mkdir(parents=True, exist_ok=True)

    video = root / "t.mp4"
    if not video.is_file():
        print(f"ERROR: expected {video} (the workflow makes it with ffmpeg)")
        return 2

    segments = []
    for i, name in enumerate(("one", "two")):
        d = root / name
        d.mkdir(exist_ok=True)
        clip = d / f"{name}.mp4"
        clip.write_bytes(video.read_bytes())
        # main + a station-owned channel + an electrode, so the forge exercises
        # the per-device output folders rather than one flat name.
        for suffix, base in (("", 10), (".alpha", 30), (".e1", 50)):
            (d / f"{name}{suffix}.funscript").write_text(
                json.dumps({"actions": [
                    {"at": t, "pos": (base + t // 10) % 100}
                    for t in range(0, 1000, 100)
                ]}),
                encoding="utf-8",
            )
        segments.append({
            "id": f"seg-{i}", "type": "segment", "video": str(clip),
            "audio": {"mode": "keep"}, "overlays": [],
            "funscripts": {"source": "auto_detect"},
            "bookmark": f"Smoke {name}",
        })

    project = {
        "version": "2.0",
        "sections": [
            {
                "id": "sec-1", "name": "First", "overlays": [],
                "leading_joiner": {"id": "j1", "type": "joiner",
                                   "joiner_type": "none", "params": {}},
                "segments": [segments[0]],
            },
            {
                "id": "sec-2", "name": "Second", "overlays": [],
                # A real joiner, so the chapter list has two entries and the
                # engine's fade path is touched.
                "leading_joiner": {"id": "j2", "type": "joiner",
                                   "joiner_type": "fade_to_black",
                                   "params": {"duration_s": 0.5, "fade_s": 0.5}},
                "segments": [segments[1]],
            },
        ],
        "output": {
            "folder": str(root / "out"), "basename": "smoke",
            "resolution": "1080p",
            "produce_video": False, "produce_funscripts": True,
            "produce_audio_estim": False, "produce_forge_bundle": True,
        },
        "audio_beds": [],
    }
    out = root / "smoke.forgeproject.json"
    out.write_text(json.dumps(project, indent=2), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
