# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Auto-detect the video and associated funscripts inside a folder.

Two common layouts:
  A) each segment in its own folder with one video:
       folder/
         clip.mp4
         clip.funscript
         clip.pitch.funscript
         clip.alpha.funscript
         clip.beta.funscript
         clip.stereostim.wav
         clip.alpha-prostate.funscript
  B) many clips in one folder, named by stem:
       folder/
         video1.mp4 + video1.funscript + video1.pitch.funscript ...
         video2.mp4 + video2.funscript + video2.pitch.funscript ...
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}
# Multi-axis axis names (FunscriptForge conventions).
MULTI_AXIS = {"pitch", "roll", "surge", "sway", "twist"}
# Estim channel suffixes.
ESTIM_3PHASE = {"alpha", "beta"}
PROSTATE = {"alpha-prostate", "beta-prostate"}
AUDIO_ESTIM_SUFFIXES = {".stereostim.wav", ".legacy.wav", ".prostate.stereostim.wav"}

__all__ = [
    "DetectedClip",
    "detect_folder",
    "detect_folder_tree",
    "detect_file",
    "funscripts_for_stem",
]


@dataclass
class DetectedClip:
    video: Path
    stem: str
    funscripts: dict[str, Path] = field(default_factory=dict)
    audio_estim: dict[str, Path] = field(default_factory=dict)

    @property
    def has_main_funscript(self) -> bool:
        return "main" in self.funscripts


def _split_ff_suffix(filename: str) -> tuple[str, str | None]:
    """Split 'clip.pitch.funscript' -> ('clip', 'pitch').
    Returns ('clip', None) for 'clip.funscript' (main script).
    """
    stem = filename
    if not stem.endswith(".funscript"):
        return stem, None
    stem = stem[: -len(".funscript")]
    # stem might still have a channel suffix: "clip.pitch"
    if "." in stem:
        base, channel = stem.rsplit(".", 1)
        return base, channel
    return stem, None


# Channel-funscript sub-folders written by FunscriptForge. When the
# video sits next to `estim/`, `multi_axis/`, etc., the non-main
# channel funscripts live inside those folders — not alongside the
# main. Detection scans the immediate folder AND each of these
# well-known sub-folders so users can point ForgeAssembler at a
# FunscriptForge output directory and get all channels picked up.
_CHANNEL_SUBFOLDERS: tuple[str, ...] = (
    "estim", "multi_axis", "prostate", "audio_estim",
)


def funscripts_for_stem(folder: Path, stem: str) -> dict[str, Path]:
    """Return a map of channel -> path for funscripts sharing `stem`.

    Keys used:
      "main"           -> stem.funscript
      "pitch" / "roll" / "surge" / "sway" / "twist" -> multi-axis
      "alpha" / "beta" -> 3-phase estim
      "alpha-prostate" / "beta-prostate" -> prostate variants
      "pulse_frequency" -> pulse-frequency funscript
      anything else is carried through under its own name.

    Scans the video's immediate folder AND well-known channel
    sub-folders (`estim/`, `multi_axis/`, `prostate/`, `audio_estim/`)
    so a FunscriptForge output layout — main funscript next to the
    .mp4, channel funscripts nested one level down — picks up every
    channel cleanly.
    """
    out: dict[str, Path] = {}
    search_dirs: list[Path] = [folder]
    for sub in _CHANNEL_SUBFOLDERS:
        d = folder / sub
        if d.is_dir():
            search_dirs.append(d)
    for d in search_dirs:
        try:
            for f in d.iterdir():
                if not f.is_file() or not f.name.endswith(".funscript"):
                    continue
                base, channel = _split_ff_suffix(f.name)
                if base != stem:
                    continue
                key = channel if channel else "main"
                # First hit wins — the main folder takes precedence
                # over any duplicate in a sub-folder.
                out.setdefault(key, f)
        except OSError:
            continue
    return out


def audio_estim_for_stem(folder: Path, stem: str) -> dict[str, Path]:
    """Find .stereostim.wav / .legacy.wav / .prostate.stereostim.wav
    siblings of `stem`. Scans the immediate folder AND well-known
    channel sub-folders (parity with `funscripts_for_stem`) so a
    FunscriptForge / restim output layout — video next to .mp4, channel
    audio nested under `audio_estim/` or `estim/` — picks up cleanly.
    """
    search_dirs: list[Path] = [folder]
    for sub in _CHANNEL_SUBFOLDERS:
        d = folder / sub
        if d.is_dir():
            search_dirs.append(d)
    out: dict[str, Path] = {}
    for d in search_dirs:
        for suffix in AUDIO_ESTIM_SUFFIXES:
            p = d / f"{stem}{suffix}"
            if p.exists():
                # First hit wins — immediate folder beats sub-folders.
                out.setdefault(suffix.lstrip("."), p)
    return out


def detect_file(video_path: str | Path) -> DetectedClip:
    """Given a single video file, return its DetectedClip with siblings."""
    p = Path(video_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(p)
    if p.suffix.lower() not in VIDEO_EXTS:
        raise ValueError(f"Not a recognized video extension: {p.suffix}")
    stem = p.stem
    folder = p.parent
    return DetectedClip(
        video=p,
        stem=stem,
        funscripts=funscripts_for_stem(folder, stem),
        audio_estim=audio_estim_for_stem(folder, stem),
    )


def detect_folder(folder_path: str | Path) -> list[DetectedClip]:
    """Return one DetectedClip per video file in the folder.

    Files are sorted by name so multi-clip folders (video1, video2, ...)
    come out in a predictable order. Works for both single-clip folders
    and many-clips-in-one-folder layouts.
    """
    folder = Path(folder_path).resolve()
    if not folder.is_dir():
        raise NotADirectoryError(folder)
    clips: list[DetectedClip] = []
    for f in sorted(folder.iterdir()):
        if not f.is_file() or f.suffix.lower() not in VIDEO_EXTS:
            continue
        clips.append(detect_file(f))
    return clips


def _natural_key(p: Path) -> tuple:
    """Sort `0, 1, 2, 10, 11` instead of lexicographic `0, 1, 10, 11, 2`."""
    try:
        return (0, int(p.name))
    except ValueError:
        return (1, p.name.lower())


def detect_folder_tree(folder_path: str | Path) -> list[DetectedClip]:
    """Return clips found in a folder OR — if the immediate folder holds
    no videos — in its numbered/named subfolders.

    Matches the convention used by `cli.py new-project`: a parent
    directory like `.forge/` with `.forge/0/0.mp4`, `.forge/1/1.mp4`,
    ... collapses into a flat clip list in natural order. Subfolders
    without videos are silently skipped. Recurses one level only; deeper
    trees need an explicit choice per level.
    """
    folder = Path(folder_path).resolve()
    if not folder.is_dir():
        raise NotADirectoryError(folder)

    direct = detect_folder(folder)
    if direct:
        return direct

    clips: list[DetectedClip] = []
    subs = sorted(
        (p for p in folder.iterdir() if p.is_dir()),
        key=_natural_key,
    )
    for sub in subs:
        try:
            clips.extend(detect_folder(sub))
        except NotADirectoryError:
            continue
    return clips


# ── Channel grouping helpers ──────────────────────────────────────────
def categorize_channels(funscripts: dict[str, Path]) -> dict[str, list[str]]:
    """Bucket detected funscript channels into the selectable groups."""
    groups: dict[str, list[str]] = {
        "main": [],
        "multi_axis": [],
        "three_phase_estim": [],
        "prostate": [],
        "pulse_frequency": [],
        "other": [],
    }
    for channel in funscripts:
        if channel == "main":
            groups["main"].append(channel)
        elif channel in MULTI_AXIS:
            groups["multi_axis"].append(channel)
        elif channel in ESTIM_3PHASE:
            groups["three_phase_estim"].append(channel)
        elif channel in PROSTATE:
            groups["prostate"].append(channel)
        elif channel == "pulse_frequency":
            groups["pulse_frequency"].append(channel)
        else:
            groups["other"].append(channel)
    return groups
