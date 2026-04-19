# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Unit tests for the project data model: serialization, validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from forgeassembler_core.project import (
    AudioLayer,
    BugOverlay,
    Joiner,
    Output,
    OutputChannels,
    Overlay,
    Project,
    PROJECT_VERSION,
    RESOLUTION_KEYS,
    Segment,
    is_still_image,
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
        output=Output(folder=str(tmp_path / "out")),
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


# ── Still images ──────────────────────────────────────────────────────
def test_is_still_image_recognizes_common_extensions():
    assert is_still_image("title.png")
    assert is_still_image("title.PNG")
    assert is_still_image("title.jpg")
    assert is_still_image("title.jpeg")
    assert is_still_image("title.webp")
    assert not is_still_image("clip.mp4")
    assert not is_still_image("clip.mov")


def test_segment_is_still():
    seg_video = Segment(id="s1", video="clip.mp4")
    seg_png = Segment(id="s2", video="card.png", still_duration_s=3.0)
    assert not seg_video.is_still()
    assert seg_png.is_still()


def test_validate_png_segment_needs_still_duration(tmp_path: Path):
    png = tmp_path / "card.png"
    png.write_bytes(b"")
    p = Project(items=[Segment(id="s1", video=str(png))])
    issues = validate(p)
    assert any(
        "still_duration_s is required" in i.message and i.level == "error"
        for i in issues
    )


def test_validate_png_segment_rejects_non_positive_duration(tmp_path: Path):
    png = tmp_path / "card.png"
    png.write_bytes(b"")
    p = Project(items=[
        Segment(id="s1", video=str(png), still_duration_s=0.0),
    ])
    issues = validate(p)
    assert any(
        "still_duration_s must be positive" in i.message for i in issues
    )


def test_validate_warns_when_still_duration_set_on_video(tmp_path: Path):
    v = _make_video(tmp_path, "a")
    p = Project(items=[
        Segment(id="s1", video=str(v), still_duration_s=3.0),
    ])
    issues = validate(p)
    assert any(
        "still_duration_s is set but the video is not a still image"
        in i.message and i.level == "warning"
        for i in issues
    )


# ── Color temperature ─────────────────────────────────────────────────
def test_validate_color_temperature_in_range(tmp_path: Path):
    v = _make_video(tmp_path, "a")
    p = Project(items=[
        Segment(id="s1", video=str(v), color_temperature_k=6500),
    ])
    issues = validate(p)
    assert not any(
        "color_temperature_k" in i.message and i.level == "error"
        for i in issues
    )


def test_validate_color_temperature_rejects_out_of_range(tmp_path: Path):
    v = _make_video(tmp_path, "a")
    p = Project(items=[
        Segment(id="s1", video=str(v), color_temperature_k=3000),
    ])
    issues = validate(p)
    assert any(
        "color_temperature_k must be between 4000 and 10000" in i.message
        for i in issues
    )


# ── Output dataclass ──────────────────────────────────────────────────
def test_output_defaults():
    o = Output()
    assert o.resolution == "1080p"
    assert o.normalize_audio is True
    assert o.produce_video is True
    assert o.produce_funscripts is True
    assert o.bug is None
    assert o.basename == "combined"


def test_output_roundtrip_bug():
    o = Output(
        folder="/tmp/out",
        resolution="uw_1440p",
        normalize_audio=False,
        produce_funscripts=False,
        bug=BugOverlay(file="/b/logo.png", corner="tl", margin_px=10, opacity=0.8),
    )
    d = o.to_dict()
    o2 = Output.from_dict(d)
    assert o2.resolution == "uw_1440p"
    assert o2.normalize_audio is False
    assert o2.produce_funscripts is False
    assert o2.bug is not None
    assert o2.bug.corner == "tl"
    assert o2.bug.margin_px == 10
    assert o2.bug.opacity == 0.8


def test_validate_produce_cannot_be_all_false(tmp_path: Path):
    v = _make_video(tmp_path, "a")
    p = Project(
        items=[Segment(id="s1", video=str(v))],
        output=Output(
            folder=str(tmp_path / "out"),
            produce_video=False,
            produce_funscripts=False,
        ),
    )
    issues = validate(p)
    assert any(
        "At least one of produce_video / produce_funscripts" in i.message
        for i in issues
    )


def test_validate_produce_one_of_is_ok(tmp_path: Path):
    v = _make_video(tmp_path, "a")
    p = Project(
        items=[Segment(id="s1", video=str(v))],
        output=Output(
            folder=str(tmp_path / "out"),
            produce_video=True,
            produce_funscripts=False,
        ),
    )
    errors = [i for i in validate(p) if i.level == "error"]
    assert not any("produce_video / produce_funscripts" in e.message for e in errors)


# ── Resolution ─────────────────────────────────────────────────────────
def test_resolution_keys_include_expected():
    for k in ("1080p", "1440p", "4k", "uw_1080p", "uw_1440p",
              "4_3_hd", "3_4_hd", "9_16_hd", "source"):
        assert k in RESOLUTION_KEYS


def test_validate_rejects_unknown_resolution(tmp_path: Path):
    v = _make_video(tmp_path, "a")
    p = Project(
        items=[Segment(id="s1", video=str(v))],
        output=Output(folder=str(tmp_path / "out"), resolution="vhs"),
    )
    issues = validate(p)
    assert any(
        "'vhs' is not one of" in i.message and i.level == "error"
        for i in issues
    )


# ── Bug overlay ────────────────────────────────────────────────────────
def test_validate_bug_corner(tmp_path: Path):
    bug = tmp_path / "b.png"
    bug.write_bytes(b"")
    v = _make_video(tmp_path, "a")
    p = Project(
        items=[Segment(id="s1", video=str(v))],
        output=Output(
            folder=str(tmp_path / "out"),
            bug=BugOverlay(file=str(bug), corner="middle"),  # type: ignore[arg-type]
        ),
    )
    issues = validate(p)
    assert any("bug.corner 'middle'" in i.message for i in issues)


def test_validate_bug_opacity_range(tmp_path: Path):
    bug = tmp_path / "b.png"
    bug.write_bytes(b"")
    v = _make_video(tmp_path, "a")
    p = Project(
        items=[Segment(id="s1", video=str(v))],
        output=Output(
            folder=str(tmp_path / "out"),
            bug=BugOverlay(file=str(bug), opacity=1.5),
        ),
    )
    issues = validate(p)
    assert any(
        "bug.opacity must be between 0.0 and 1.0" in i.message for i in issues
    )


def test_validate_bug_missing_file_warns(tmp_path: Path):
    v = _make_video(tmp_path, "a")
    p = Project(
        items=[Segment(id="s1", video=str(v))],
        output=Output(
            folder=str(tmp_path / "out"),
            bug=BugOverlay(file=str(tmp_path / "nope.png")),
        ),
    )
    issues = validate(p)
    assert any(
        "Bug overlay file not found" in i.message and i.level == "warning"
        for i in issues
    )


# ── Full roundtrip with new fields ────────────────────────────────────
def test_project_full_roundtrip_with_new_fields(tmp_path: Path):
    v = _make_video(tmp_path, "a")
    png = tmp_path / "card.png"
    png.write_bytes(b"")
    bug = tmp_path / "bug.png"
    bug.write_bytes(b"")
    p = Project(
        items=[
            Segment(id="s1", video=str(png), still_duration_s=2.0),
            Joiner(id="j1", joiner_type="fade_to_black",
                   params={"duration_s": 1.0}),
            Segment(id="s2", video=str(v), color_temperature_k=5200),
        ],
        output=Output(
            folder=str(tmp_path / "out"),
            resolution="uw_1080p",
            produce_funscripts=False,
            bug=BugOverlay(file=str(bug), corner="bl"),
        ),
    )
    path = tmp_path / "project.json"
    p.save(path)
    loaded = Project.load(path)
    assert loaded.output.resolution == "uw_1080p"
    assert loaded.output.produce_funscripts is False
    assert loaded.output.bug is not None
    assert loaded.output.bug.corner == "bl"
    s1 = loaded.items[0]
    s2 = loaded.items[2]
    assert isinstance(s1, Segment)
    assert s1.still_duration_s == 2.0
    assert isinstance(s2, Segment)
    assert s2.color_temperature_k == 5200
