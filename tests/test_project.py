# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Unit tests for the project data model: serialization, validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from forgeassembler_core.project import (
    AudioLayer,
    Joiner,
    OutputChannels,
    Overlay,
    Project,
    PROJECT_VERSION,
    Segment,
    new_id,
    validate,
)


def _make_video(tmp: Path, name: str) -> Path:
    p = tmp / f"{name}.mp4"
    p.write_bytes(b"not a real video")
    return p


def test_new_id_unique():
    ids = {new_id() for _ in range(100)}
    assert len(ids) == 100


def test_project_roundtrip(tmp_path: Path):
    v1 = _make_video(tmp_path, "clip1")
    v2 = _make_video(tmp_path, "clip2")
    p = Project(
        items=[
            Segment(id="s1", video=str(v1)),
            Joiner(id="j1", joiner_type="fade_to_black",
                   params={"duration_s": 1.5}),
            Segment(
                id="s2",
                video=str(v2),
                audio=AudioLayer(mode="silence"),
                overlays=[Overlay(type="text", content="Hello", size=64)],
            ),
        ],
        output_channels=OutputChannels(main=True, multi_axis=True),
        output_folder=str(tmp_path / "out"),
    )
    data = p.to_dict()
    assert data["version"] == PROJECT_VERSION
    assert len(data["items"]) == 3

    roundtripped = Project.from_dict(data)
    assert len(roundtripped.items) == 3
    assert isinstance(roundtripped.items[0], Segment)
    assert isinstance(roundtripped.items[1], Joiner)
    seg2 = roundtripped.items[2]
    assert isinstance(seg2, Segment)
    assert seg2.audio.mode == "silence"
    assert seg2.overlays[0].content == "Hello"


def test_project_save_load(tmp_path: Path):
    v1 = _make_video(tmp_path, "a")
    p = Project(items=[Segment(id="s1", video=str(v1))])
    path = tmp_path / "project.json"
    p.save(path)
    loaded = Project.load(path)
    assert loaded.items[0].video == str(v1)


def test_output_channels_selected_order():
    oc = OutputChannels(main=True, multi_axis=True, three_phase_estim=False)
    assert "main" in oc.selected()
    assert "multi_axis" in oc.selected()
    assert "three_phase_estim" not in oc.selected()


def test_validate_requires_segments():
    p = Project(items=[])
    issues = validate(p)
    assert any(i.level == "error" and "no items" in i.message.lower() for i in issues)


def test_validate_missing_video(tmp_path: Path):
    p = Project(items=[Segment(id="s1", video=str(tmp_path / "nope.mp4"))])
    issues = validate(p)
    assert any("not found" in i.message.lower() for i in issues)


def test_validate_joiner_must_follow_segment(tmp_path: Path):
    v1 = _make_video(tmp_path, "a")
    p = Project(items=[
        Joiner(id="j1", joiner_type="none"),
        Segment(id="s1", video=str(v1)),
    ])
    issues = validate(p)
    assert any("must follow a segment" in i.message for i in issues)


def test_validate_cannot_end_with_joiner(tmp_path: Path):
    v1 = _make_video(tmp_path, "a")
    p = Project(items=[
        Segment(id="s1", video=str(v1)),
        Joiner(id="j1", joiner_type="none"),
    ])
    issues = validate(p)
    assert any("cannot end with a joiner" in i.message for i in issues)


def test_validate_fade_needs_positive_duration(tmp_path: Path):
    v1 = _make_video(tmp_path, "a")
    v2 = _make_video(tmp_path, "b")
    p = Project(items=[
        Segment(id="s1", video=str(v1)),
        Joiner(id="j1", joiner_type="fade_to_black", params={"duration_s": 0}),
        Segment(id="s2", video=str(v2)),
    ])
    issues = validate(p)
    assert any("must be positive" in i.message for i in issues)


def test_validate_audio_replace_requires_file(tmp_path: Path):
    v1 = _make_video(tmp_path, "a")
    p = Project(items=[
        Segment(id="s1", video=str(v1), audio=AudioLayer(mode="replace")),
    ])
    issues = validate(p)
    assert any("requires audio.file" in i.message for i in issues)
