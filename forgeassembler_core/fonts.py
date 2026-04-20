# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Enumerate system fonts for the text-overlay picker.

Scans platform-specific font directories for .ttf / .otf / .ttc files
and returns a sorted, de-duplicated list of `(stem, full_path)` pairs.
The UI shows stems in the dropdown; the engine passes the full path
to ffmpeg's drawtext `fontfile=` argument.

Design notes
------------
- Pure filesystem walk — no external library (no matplotlib,
  fontconfig). Keeps PyInstaller bundles lean.
- Multiple fonts may share a stem (e.g. "Arial" appears in
  `C:\\Windows\\Fonts\\arial.ttf` and a user's personal Fonts
  folder). The first match wins; later duplicates are dropped.
- `resolve_font_path(stem)` returns the full path for a chosen stem,
  or None when the system doesn't have that font installed. The
  engine calls this at forge time so stems stay portable across
  machines (a project opened on a different OS still renders as long
  as an equivalently-named font exists).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterator

_FONT_SUFFIXES: tuple[str, ...] = (".ttf", ".otf", ".ttc")


def _candidate_dirs() -> list[Path]:
    """Return the platform-specific font directories to scan."""
    dirs: list[Path] = []
    if sys.platform.startswith("win"):
        windir = os.environ.get("WINDIR", r"C:\Windows")
        dirs.append(Path(windir) / "Fonts")
        # Per-user fonts on Windows 10+ (opt-in "Install for me only").
        local = os.environ.get("LOCALAPPDATA")
        if local:
            dirs.append(Path(local) / "Microsoft" / "Windows" / "Fonts")
    elif sys.platform == "darwin":
        dirs.extend([
            Path("/System/Library/Fonts"),
            Path("/Library/Fonts"),
            Path.home() / "Library" / "Fonts",
        ])
    else:  # Linux / BSD
        dirs.extend([
            Path("/usr/share/fonts"),
            Path("/usr/local/share/fonts"),
            Path.home() / ".fonts",
            Path.home() / ".local" / "share" / "fonts",
        ])
    return [d for d in dirs if d.exists() and d.is_dir()]


def _walk_font_files(directory: Path) -> Iterator[Path]:
    """Yield every font file under `directory`, recursively."""
    try:
        for dirpath, _dirs, filenames in os.walk(directory):
            for name in filenames:
                lower = name.lower()
                if lower.endswith(_FONT_SUFFIXES):
                    yield Path(dirpath) / name
    except OSError:
        return


def list_fonts() -> list[tuple[str, str]]:
    """Return `[(stem, full_path), ...]` sorted by stem, de-duplicated.

    Stem = filename without extension. A later stem collision is
    silently skipped (first one wins).
    """
    seen: dict[str, str] = {}
    for d in _candidate_dirs():
        for p in _walk_font_files(d):
            stem = p.stem
            if stem not in seen:
                seen[stem] = str(p)
    return sorted(seen.items())


def resolve_font_path(stem: str) -> str | None:
    """Return the full filesystem path for a font stem, or None when
    no such font is installed on this machine.
    """
    if not stem:
        return None
    for candidate_stem, path in list_fonts():
        if candidate_stem == stem:
            return path
    return None
