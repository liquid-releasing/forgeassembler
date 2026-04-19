# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""CLI smoke tests — exit codes, output, no-op dry runs."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
CLI = [sys.executable, str(REPO / "cli.py")]


def run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        CLI + list(args),
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
    )


def test_version():
    r = run("--version")
    assert r.returncode == 0
    assert "ForgeAssembler" in r.stdout


def test_list_joiners_shows_core_types():
    r = run("list-joiners")
    assert r.returncode == 0
    assert "none" in r.stdout
    assert "fade_to_black" in r.stdout
    assert "duration_s" in r.stdout


def test_detect_empty_folder(tmp_path: Path):
    r = run("detect", str(tmp_path))
    assert r.returncode == 0
    assert "No video files" in r.stdout


def test_detect_folder_with_clip(tmp_path: Path):
    (tmp_path / "clip.mp4").write_bytes(b"")
    (tmp_path / "clip.funscript").write_text(
        json.dumps({"actions": []}), encoding="utf-8"
    )
    (tmp_path / "clip.pitch.funscript").write_text(
        json.dumps({"actions": []}), encoding="utf-8"
    )
    r = run("detect", str(tmp_path))
    assert r.returncode == 0
    assert "clip" in r.stdout
    assert "multi_axis" in r.stdout


def test_validate_missing_file():
    r = run("validate", "does-not-exist.json")
    assert r.returncode == 2


def test_validate_empty_project(tmp_path: Path):
    p = tmp_path / "empty.forgeproject.json"
    p.write_text(json.dumps({"version": "1.0", "items": []}), encoding="utf-8")
    r = run("validate", str(p))
    assert r.returncode == 1
    assert "no items" in r.stderr.lower()


def test_validate_simple_project(tmp_path: Path):
    vid = tmp_path / "a.mp4"
    vid.write_bytes(b"")
    p = tmp_path / "ok.forgeproject.json"
    p.write_text(
        json.dumps({
            "version": "1.0",
            "items": [{"id": "s1", "type": "segment", "video": str(vid)}],
            "output": {"folder": str(tmp_path / "out")},
        }),
        encoding="utf-8",
    )
    r = run("validate", str(p))
    assert r.returncode == 0


def test_forge_fails_cleanly_on_unreadable_video(tmp_path: Path):
    """A zero-byte 'video' can't be probed — forge should exit non-zero
    with an error, not crash."""
    vid = tmp_path / "a.mp4"
    vid.write_bytes(b"")
    p = tmp_path / "p.forgeproject.json"
    p.write_text(
        json.dumps({
            "version": "1.0",
            "items": [{"id": "s1", "type": "segment", "video": str(vid)}],
            "output": {"folder": str(tmp_path / "out")},
        }),
        encoding="utf-8",
    )
    r = run("forge", str(p))
    assert r.returncode != 0
    assert "ERROR" in r.stderr


def test_forge_rejects_no_video_and_no_funscripts_together(tmp_path: Path):
    vid = tmp_path / "a.mp4"
    vid.write_bytes(b"")
    p = tmp_path / "p.forgeproject.json"
    p.write_text(
        json.dumps({
            "version": "1.0",
            "items": [{"id": "s1", "type": "segment", "video": str(vid)}],
            "output": {"folder": str(tmp_path / "out")},
        }),
        encoding="utf-8",
    )
    r = run("forge", str(p), "--no-video", "--no-funscripts")
    assert r.returncode != 0
    assert "cannot both be set" in r.stderr
