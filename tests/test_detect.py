# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Unit tests for folder detection: single-folder and many-clips layouts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from forgeassembler_core.detect import (
    categorize_channels,
    detect_file,
    detect_folder,
    detect_folder_tree,
    funscripts_for_stem,
)


def _touch(p: Path, content: str = "") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _stub_funscript(p: Path) -> Path:
    return _touch(p, json.dumps({"actions": [{"at": 0, "pos": 0}]}))


def test_single_folder_clip(tmp_path: Path):
    _touch(tmp_path / "clip.mp4")
    _stub_funscript(tmp_path / "clip.funscript")
    _stub_funscript(tmp_path / "clip.pitch.funscript")
    _stub_funscript(tmp_path / "clip.alpha.funscript")

    clips = detect_folder(tmp_path)
    assert len(clips) == 1
    c = clips[0]
    assert c.stem == "clip"
    assert "main" in c.funscripts
    assert "pitch" in c.funscripts
    assert "alpha" in c.funscripts


def test_many_clips_same_folder(tmp_path: Path):
    _touch(tmp_path / "video1.mp4")
    _stub_funscript(tmp_path / "video1.funscript")
    _touch(tmp_path / "video2.mp4")
    _stub_funscript(tmp_path / "video2.funscript")
    _stub_funscript(tmp_path / "video2.pitch.funscript")

    clips = detect_folder(tmp_path)
    assert [c.stem for c in clips] == ["video1", "video2"]
    v1 = clips[0]
    v2 = clips[1]
    assert "main" in v1.funscripts
    assert "pitch" not in v1.funscripts
    assert "pitch" in v2.funscripts


def test_detect_file_returns_siblings(tmp_path: Path):
    video = _touch(tmp_path / "clip.mp4")
    _stub_funscript(tmp_path / "clip.funscript")
    _stub_funscript(tmp_path / "clip.roll.funscript")
    clip = detect_file(video)
    assert clip.stem == "clip"
    assert "roll" in clip.funscripts


def test_detect_file_rejects_non_video(tmp_path: Path):
    txt = _touch(tmp_path / "clip.txt")
    with pytest.raises(ValueError):
        detect_file(txt)


def test_funscripts_for_stem_filters_correctly(tmp_path: Path):
    # Create funscripts for two stems; verify we only return one stem's set.
    _stub_funscript(tmp_path / "alice.funscript")
    _stub_funscript(tmp_path / "alice.pitch.funscript")
    _stub_funscript(tmp_path / "bob.funscript")
    _stub_funscript(tmp_path / "bob.alpha.funscript")

    alice = funscripts_for_stem(tmp_path, "alice")
    assert set(alice.keys()) == {"main", "pitch"}
    bob = funscripts_for_stem(tmp_path, "bob")
    assert set(bob.keys()) == {"main", "alpha"}


def test_funscripts_for_stem_scans_channel_subfolders(tmp_path: Path):
    """FunscriptForge writes main funscript next to the .mp4 but
    nests estim/multi-axis/prostate channel funscripts into
    sub-folders. Detection should reach into those sub-folders so
    every channel is picked up."""
    _stub_funscript(tmp_path / "0.funscript")  # main, at root
    (tmp_path / "estim").mkdir()
    _stub_funscript(tmp_path / "estim" / "0.alpha.funscript")
    _stub_funscript(tmp_path / "estim" / "0.beta.funscript")
    (tmp_path / "multi_axis").mkdir()
    _stub_funscript(tmp_path / "multi_axis" / "0.pitch.funscript")
    _stub_funscript(tmp_path / "multi_axis" / "0.roll.funscript")
    (tmp_path / "prostate").mkdir()
    _stub_funscript(tmp_path / "prostate" / "0.alpha-prostate.funscript")

    found = funscripts_for_stem(tmp_path, "0")
    assert set(found.keys()) == {
        "main", "alpha", "beta", "pitch", "roll", "alpha-prostate",
    }


def test_funscripts_for_stem_root_wins_over_subfolder_dupe(tmp_path: Path):
    """If the same channel shows up in both the root and a sub-folder
    (shouldn't normally happen, but defensive), the root takes
    precedence."""
    root_main = tmp_path / "0.funscript"
    _stub_funscript(root_main)
    (tmp_path / "estim").mkdir()
    _stub_funscript(tmp_path / "estim" / "0.funscript")
    found = funscripts_for_stem(tmp_path, "0")
    assert found["main"] == root_main


def test_categorize_channels():
    # Fabricate paths for category testing; they don't have to exist.
    fake = {
        "main": Path("x.funscript"),
        "pitch": Path("x.pitch.funscript"),
        "roll": Path("x.roll.funscript"),
        "alpha": Path("x.alpha.funscript"),
        "beta": Path("x.beta.funscript"),
        "alpha-prostate": Path("x.alpha-prostate.funscript"),
        "pulse_frequency": Path("x.pulse_frequency.funscript"),
        "mystery": Path("x.mystery.funscript"),
    }
    groups = categorize_channels(fake)
    assert groups["main"] == ["main"]
    assert set(groups["multi_axis"]) == {"pitch", "roll"}
    assert set(groups["three_phase_estim"]) == {"alpha", "beta"}
    assert groups["prostate"] == ["alpha-prostate"]
    assert groups["pulse_frequency"] == ["pulse_frequency"]
    assert groups["other"] == ["mystery"]


def test_detect_folder_missing(tmp_path: Path):
    bogus = tmp_path / "does-not-exist"
    with pytest.raises(NotADirectoryError):
        detect_folder(bogus)


# ── detect_folder_tree (subfolder recursion) ──────────────────────────
def test_detect_folder_tree_returns_direct_when_present(tmp_path: Path):
    """Prefer direct videos over descending into subfolders."""
    _touch(tmp_path / "top.mp4")
    (tmp_path / "sub").mkdir()
    _touch(tmp_path / "sub" / "nested.mp4")
    clips = detect_folder_tree(tmp_path)
    assert [c.video.name for c in clips] == ["top.mp4"]


def test_detect_folder_tree_recurses_when_parent_empty(tmp_path: Path):
    """Matches the new-project CLI's `.forge/0/0.mp4` convention —
    videos live one level down from a parent that has none directly."""
    # Create 0/, 1/, 2/, 10/, 11/ each with a video
    for idx in ("0", "1", "2", "10", "11"):
        sub = tmp_path / idx
        sub.mkdir()
        _touch(sub / f"{idx}.mp4")
    clips = detect_folder_tree(tmp_path)
    # Natural sort: 0, 1, 2, 10, 11 (not lexicographic 0, 1, 10, 11, 2)
    assert [c.video.stem for c in clips] == ["0", "1", "2", "10", "11"]


def test_detect_folder_tree_skips_empty_subfolders(tmp_path: Path):
    (tmp_path / "0").mkdir()
    _touch(tmp_path / "0" / "0.mp4")
    (tmp_path / "1").mkdir()  # empty — should be skipped silently
    (tmp_path / "2").mkdir()
    _touch(tmp_path / "2" / "later.mp4")
    clips = detect_folder_tree(tmp_path)
    assert [c.video.name for c in clips] == ["0.mp4", "later.mp4"]


def test_detect_folder_tree_missing_raises(tmp_path: Path):
    with pytest.raises(NotADirectoryError):
        detect_folder_tree(tmp_path / "nope")
