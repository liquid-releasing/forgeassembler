# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Unit tests for forgeassembler_core.fonts."""

from __future__ import annotations

from pathlib import Path

import pytest

from forgeassembler_core import fonts as fonts_mod


def test_list_fonts_is_sorted_and_deduped(tmp_path: Path, monkeypatch):
    """list_fonts walks the candidate dirs and returns (stem, path)
    pairs sorted by stem, with duplicates collapsed (first path wins)."""
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir(); dir_b.mkdir()
    (dir_a / "Zeta.ttf").write_bytes(b"")
    (dir_a / "Alpha.otf").write_bytes(b"")
    # Same stem in dir_b — should be dropped (first wins).
    (dir_b / "Alpha.ttf").write_bytes(b"")
    (dir_b / "Beta.ttc").write_bytes(b"")

    monkeypatch.setattr(fonts_mod, "_candidate_dirs", lambda: [dir_a, dir_b])

    fonts = fonts_mod.list_fonts()
    stems = [s for s, _ in fonts]
    assert stems == ["Alpha", "Beta", "Zeta"]
    # Alpha points at dir_a, not dir_b (first match wins).
    alpha_path = dict(fonts)["Alpha"]
    assert str(dir_a) in alpha_path


def test_list_fonts_ignores_non_font_files(tmp_path: Path, monkeypatch):
    """Files with other extensions are skipped; only .ttf/.otf/.ttc
    get picked up."""
    d = tmp_path / "fonts"
    d.mkdir()
    (d / "actually.ttf").write_bytes(b"")
    (d / "readme.txt").write_bytes(b"")
    (d / "image.png").write_bytes(b"")

    monkeypatch.setattr(fonts_mod, "_candidate_dirs", lambda: [d])
    fonts = fonts_mod.list_fonts()
    assert [s for s, _ in fonts] == ["actually"]


def test_resolve_font_path_hits_and_misses(tmp_path: Path, monkeypatch):
    d = tmp_path / "fonts"
    d.mkdir()
    (d / "FindMe.ttf").write_bytes(b"")
    monkeypatch.setattr(fonts_mod, "_candidate_dirs", lambda: [d])

    assert fonts_mod.resolve_font_path("FindMe") is not None
    assert fonts_mod.resolve_font_path("NotThere") is None
    # Empty stem returns None without scanning.
    assert fonts_mod.resolve_font_path("") is None


def test_list_fonts_recurses_into_subdirectories(tmp_path: Path, monkeypatch):
    """macOS/Linux nest fonts inside subfolders under /usr/share/fonts
    etc — the walk must be recursive."""
    d = tmp_path / "fonts"
    nested = d / "truetype" / "noto"
    nested.mkdir(parents=True)
    (nested / "NotoSans.ttf").write_bytes(b"")
    monkeypatch.setattr(fonts_mod, "_candidate_dirs", lambda: [d])
    fonts = fonts_mod.list_fonts()
    assert ("NotoSans" in [s for s, _ in fonts])
