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


def test_resolve_font_path_is_case_insensitive(tmp_path: Path, monkeypatch):
    """`arial.ttf` gives the stem "arial", but a project may well say
    "Arial" — which used to resolve to None and silently fall through to
    the fallback font."""
    d = tmp_path / "fonts"
    d.mkdir()
    (d / "arial.ttf").write_bytes(b"")
    monkeypatch.setattr(fonts_mod, "_candidate_dirs", lambda: [d])

    for spelling in ("arial", "Arial", "ARIAL", "ArIaL"):
        assert fonts_mod.resolve_font_path(spelling) is not None, spelling
    assert fonts_mod.resolve_font_path("Helvetica") is None


def test_resolve_font_path_prefers_an_exact_match(tmp_path: Path, monkeypatch):
    """Two fonts differing only in case: the exact spelling wins, so a
    deliberate choice is never folded into its neighbour."""
    d = tmp_path / "fonts"
    d.mkdir()
    (d / "CASED.ttf").write_bytes(b"")
    (d / "cased.otf").write_bytes(b"")
    monkeypatch.setattr(fonts_mod, "_candidate_dirs", lambda: [d])

    assert fonts_mod.resolve_font_path("cased").endswith("cased.otf")
    assert fonts_mod.resolve_font_path("CASED").endswith("CASED.ttf")


def test_fallback_is_a_readable_sans_not_the_first_alphabetically(
    tmp_path: Path, monkeypatch,
):
    """The regression this exists for: the old fallback was
    `list_fonts()[0]`, which on Windows is AGENCYB (Agency FB Bold) — a
    narrow condensed face that rendered a real credits roll."""
    d = tmp_path / "fonts"
    d.mkdir()
    (d / "AGENCYB.ttf").write_bytes(b"")
    (d / "arial.ttf").write_bytes(b"")
    (d / "Wingdings.ttf").write_bytes(b"")
    monkeypatch.setattr(fonts_mod, "_candidate_dirs", lambda: [d])

    assert fonts_mod.preferred_font_stem() == "arial"
    assert fonts_mod.fallback_font_path().endswith("arial.ttf")


def test_fallback_settles_for_what_there_is(tmp_path: Path, monkeypatch):
    """With none of the preferred faces installed, take the first rather
    than render nothing — but say so by ordering, not by accident."""
    d = tmp_path / "fonts"
    d.mkdir()
    (d / "Obscure.ttf").write_bytes(b"")
    monkeypatch.setattr(fonts_mod, "_candidate_dirs", lambda: [d])
    assert fonts_mod.preferred_font_stem() == "Obscure"
    assert fonts_mod.fallback_font_path().endswith("Obscure.ttf")


def test_fallback_with_no_fonts_at_all(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(fonts_mod, "_candidate_dirs", lambda: [])
    assert fonts_mod.preferred_font_stem() is None
    assert fonts_mod.fallback_font_path() is None
