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
    # Migration turns an empty v1 items list into a single empty
    # section; validate then flags "no segments".
    assert "no segments" in r.stderr.lower()


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


def test_new_project_scans_subfolders(tmp_path: Path):
    """new-project walks subfolders, emits ONE section with every
    detected clip as a cut-joined segment, natural-sorted."""
    root = tmp_path / "pieces"
    root.mkdir()
    # Create 0, 1, 2, 10, 11 (tests natural sort: 0,1,2,10,11 not 0,1,10,11,2)
    for idx in ("0", "1", "2", "10", "11"):
        sub = root / idx
        sub.mkdir()
        video = sub / f"{idx}.mp4"
        video.write_bytes(b"")
        fs = sub / f"{idx}.funscript"
        fs.write_text(json.dumps({"actions": []}), encoding="utf-8")

    out_json = tmp_path / "proj.forgeproject.json"
    r = run("new-project", str(root), str(out_json))
    assert r.returncode == 0, r.stderr
    assert out_json.exists()

    data = json.loads(out_json.read_text(encoding="utf-8"))
    # v2.0 format: one section with all clips
    assert data["version"] == "2.0"
    assert len(data["sections"]) == 1
    section = data["sections"][0]
    assert section["leading_joiner"]["joiner_type"] == "none"
    segments = section["segments"]
    assert len(segments) == 5
    # Natural sort: 0, 1, 2, 10, 11 in that order
    names_in_order = [Path(s["video"]).stem for s in segments]
    assert names_in_order == ["0", "1", "2", "10", "11"]


def test_new_project_skips_empty_subfolders(tmp_path: Path):
    root = tmp_path / "mixed"
    root.mkdir()
    # One clip, two empties
    (root / "0").mkdir()
    vid = root / "0" / "0.mp4"
    vid.write_bytes(b"")
    (root / "0" / "0.funscript").write_text(
        json.dumps({"actions": []}), encoding="utf-8",
    )
    (root / "1").mkdir()  # empty
    (root / "2").mkdir()  # empty

    out_json = tmp_path / "proj.forgeproject.json"
    r = run("new-project", str(root), str(out_json))
    assert r.returncode == 0
    assert "skipped 2 subfolder(s)" in r.stdout
    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert len(data["sections"]) == 1
    assert len(data["sections"][0]["segments"]) == 1


def test_new_project_error_when_no_clips(tmp_path: Path):
    root = tmp_path / "empties"
    root.mkdir()
    (root / "0").mkdir()
    (root / "1").mkdir()
    r = run("new-project", str(root), str(tmp_path / "p.json"))
    assert r.returncode == 2
    assert "no clips detected" in r.stderr.lower()


# ── JSON surfaces consumed by the Tauri bridge ────────────────────────
def test_list_joiners_json():
    r = run("list-joiners", "--format", "json")
    assert r.returncode == 0
    payload = json.loads(r.stdout)
    types = {j["joiner_type"] for j in payload["joiners"]}
    assert {"none", "fade_to_black"} <= types
    fade = next(j for j in payload["joiners"] if j["joiner_type"] == "fade_to_black")
    assert "duration_s" in fade["params_schema"]


def test_detect_json_empty(tmp_path: Path):
    r = run("detect", str(tmp_path), "--format", "json")
    assert r.returncode == 0
    assert json.loads(r.stdout) == {"clips": []}


def test_detect_json_with_clip(tmp_path: Path):
    (tmp_path / "clip.mp4").write_bytes(b"")
    (tmp_path / "clip.funscript").write_text(
        json.dumps({"actions": []}), encoding="utf-8"
    )
    (tmp_path / "clip.pitch.funscript").write_text(
        json.dumps({"actions": []}), encoding="utf-8"
    )
    r = run("detect", str(tmp_path), "--format", "json")
    assert r.returncode == 0
    clips = json.loads(r.stdout)["clips"]
    assert len(clips) == 1
    clip = clips[0]
    assert clip["stem"] == "clip"
    assert "main" in clip["funscripts"]
    assert "pitch" in clip["funscripts"]
    assert "multi_axis" in clip["channel_groups"]


def test_validate_json_missing_file():
    r = run("validate", "nope.json", "--format", "json")
    assert r.returncode == 2
    payload = json.loads(r.stdout)
    assert payload["ok"] is False
    assert payload["errors"]


def test_validate_json_ok(tmp_path: Path):
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
    r = run("validate", str(p), "--format", "json")
    assert r.returncode == 0
    payload = json.loads(r.stdout)
    assert payload["ok"] is True
    assert payload["segment_count"] == 1


def test_forge_rejects_all_produce_flags_off_together(tmp_path: Path):
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
    r = run(
        "forge", str(p),
        "--no-video", "--no-funscripts", "--no-audio-estim",
    )
    assert r.returncode != 0
    assert "cannot all be set" in r.stderr
