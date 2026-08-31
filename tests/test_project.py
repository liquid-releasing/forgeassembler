# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Unit tests for the project data model: serialization, validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from forgeassembler_core.project import (
    AudioLayer,
    BugOverlay,
    FRAME_RATE_KEYS,
    Joiner,
    Metadata,
    Output,
    OutputChannels,
    Overlay,
    Project,
    PROJECT_VERSION,
    QUALITY_CRF,
    RESOLUTION_KEYS,
    Section,
    SectionOverlay,
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
    # v2.0 migrates the flat items list into sections: the fade_to_black
    # joiner splits them into two sections (s1 alone, then s2).
    assert len(data["sections"]) == 2

    roundtripped = Project.from_dict(data)
    assert len(roundtripped.sections) == 2
    assert roundtripped.sections[0].segments[0].id == "s1"
    assert roundtripped.sections[1].leading_joiner.joiner_type == "fade_to_black"
    seg2 = roundtripped.sections[1].segments[0]
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
    p = Project()
    issues = validate(p)
    assert any(
        i.level == "error" and "no sections" in i.message.lower()
        for i in issues
    )


def test_validate_missing_video(tmp_path: Path):
    p = Project(items=[Segment(id="s1", video=str(tmp_path / "nope.mp4"))])
    issues = validate(p)
    assert any("not found" in i.message.lower() for i in issues)


def test_validate_warns_on_empty_section(tmp_path: Path):
    """An empty section is a warning (user may be about to populate it)."""
    from forgeassembler_core.project import Section
    v1 = _make_video(tmp_path, "a")
    p = Project(sections=[
        Section(id="sec1", segments=[Segment(id="s1", video=str(v1))]),
        Section(id="sec2"),  # empty → warning
    ])
    issues = validate(p)
    assert any(
        i.level == "warning" and "has no segments" in i.message and i.item_id == "sec2"
        for i in issues
    )


def test_legacy_items_migrate_to_sections(tmp_path: Path):
    """Passing `items=` on construction routes through the v1 migration.
    Non-'none' joiners start new sections; 'none' joiners are absorbed."""
    v1 = _make_video(tmp_path, "a")
    v2 = _make_video(tmp_path, "b")
    v3 = _make_video(tmp_path, "c")
    p = Project(items=[
        Segment(id="s1", video=str(v1)),
        Joiner(id="j1", joiner_type="none"),           # absorbed
        Segment(id="s2", video=str(v2)),
        Joiner(id="j2", joiner_type="fade_to_black",
               params={"duration_s": 1.0}),             # boundary
        Segment(id="s3", video=str(v3)),
    ])
    # Two sections: s1+s2 together (cut-joined), then s3 behind a fade
    assert len(p.sections) == 2
    assert [s.id for s in p.sections[0].segments] == ["s1", "s2"]
    assert p.sections[0].leading_joiner.joiner_type == "none"
    assert [s.id for s in p.sections[1].segments] == ["s3"]
    assert p.sections[1].leading_joiner.joiner_type == "fade_to_black"


def test_validate_fade_needs_positive_duration(tmp_path: Path):
    """With fade/hold decoupled, a joiner can't be a no-op — hold=0
    AND fade=0 is rejected. Hold=0 alone (crossfade-through-black) is
    now valid as long as fade_s > 0."""
    v1 = _make_video(tmp_path, "a")
    v2 = _make_video(tmp_path, "b")
    p = Project(items=[
        Segment(id="s1", video=str(v1)),
        Joiner(
            id="j1", joiner_type="fade_to_black",
            params={"duration_s": 0, "fade_s": 0},
        ),
        Segment(id="s2", video=str(v2)),
    ])
    issues = validate(p)
    assert any("no-op" in i.message for i in issues)


def test_validate_fade_accepts_zero_hold_with_positive_fade(tmp_path: Path):
    """Hold=0 + fade=1 is a valid pure crossfade through black."""
    v1 = _make_video(tmp_path, "a")
    v2 = _make_video(tmp_path, "b")
    p = Project(items=[
        Segment(id="s1", video=str(v1)),
        Joiner(
            id="j1", joiner_type="fade_to_black",
            params={"duration_s": 0, "fade_s": 1.0},
        ),
        Segment(id="s2", video=str(v2)),
    ])
    issues = validate(p)
    errors = [i for i in issues if i.level == "error"]
    # Sub-filter to joiner-related issues only (other warnings may exist).
    joiner_errors = [i for i in errors if "fade_to_black" in i.message]
    assert joiner_errors == []


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
            produce_audio_estim=False,
        ),
    )
    issues = validate(p)
    assert any(
        "produce_video / produce_funscripts / produce_audio_estim"
        in i.message
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
            produce_audio_estim=False,
        ),
    )
    errors = [i for i in validate(p) if i.level == "error"]
    assert not any("produce_video" in e.message for e in errors)


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


# ── Segment background ────────────────────────────────────────────────
def test_segment_background_default_is_black(tmp_path: Path):
    seg = Segment(id="s1", video=str(tmp_path / "a.mp4"))
    assert seg.background == "black"


def test_segment_background_previous_last_frame_roundtrip(tmp_path: Path):
    png = tmp_path / "card.png"
    png.write_bytes(b"")
    seg = Segment(
        id="s1", video=str(png),
        still_duration_s=2.0,
        background="previous_last_frame",
    )
    d = seg.to_dict()
    assert d["background"] == "previous_last_frame"
    seg2 = Segment.from_dict(d)
    assert seg2.background == "previous_last_frame"


def test_segment_background_black_omitted_from_dict(tmp_path: Path):
    """Default 'black' doesn't appear in serialized output to keep
    existing JSON files clean."""
    seg = Segment(id="s1", video=str(tmp_path / "a.mp4"))
    assert "background" not in seg.to_dict()


def test_validate_previous_last_frame_requires_still(tmp_path: Path):
    v1 = _make_video(tmp_path, "a")
    v2 = _make_video(tmp_path, "b")
    p = Project(items=[
        Segment(id="s1", video=str(v1)),
        Segment(id="s2", video=str(v2), background="previous_last_frame"),
    ])
    issues = validate(p)
    assert any(
        "background=previous_last_frame is only supported for "
        "still-image segments" in i.message and i.level == "error"
        for i in issues
    )


def test_validate_previous_last_frame_requires_preceding_segment(tmp_path: Path):
    png = tmp_path / "card.png"
    png.write_bytes(b"")
    p = Project(items=[
        Segment(
            id="s1", video=str(png),
            still_duration_s=2.0,
            background="previous_last_frame",
        ),
    ])
    issues = validate(p)
    assert any(
        "requires a preceding segment" in i.message and i.level == "error"
        for i in issues
    )


def test_validate_previous_last_frame_happy_path(tmp_path: Path):
    v = _make_video(tmp_path, "a")
    png = tmp_path / "card.png"
    png.write_bytes(b"")
    p = Project(
        items=[
            Segment(id="s1", video=str(v)),
            Segment(
                id="s2", video=str(png),
                still_duration_s=2.0,
                background="previous_last_frame",
            ),
        ],
        output=Output(folder=str(tmp_path / "out")),
    )
    errors = [i for i in validate(p) if i.level == "error"]
    assert not any(
        "previous_last_frame" in e.message for e in errors
    )


# ── Quality preset ────────────────────────────────────────────────────
def test_quality_default_is_medium():
    assert Output().quality == "medium"


def test_quality_crf_mapping():
    assert Output(quality="high").crf() == 18
    assert Output(quality="medium").crf() == 23
    assert Output(quality="low").crf() == 28


def test_quality_crf_falls_back_for_unknown():
    # crf() returns the medium fallback for unknown values (validate
    # catches the bad key at the top level).
    assert Output(quality="silly").crf() == 23


def test_quality_roundtrip():
    o = Output(quality="low")
    o2 = Output.from_dict(o.to_dict())
    assert o2.quality == "low"


def test_validate_rejects_unknown_quality(tmp_path: Path):
    v = _make_video(tmp_path, "a")
    p = Project(
        items=[Segment(id="s1", video=str(v))],
        output=Output(folder=str(tmp_path / "out"), quality="ultra"),
    )
    issues = validate(p)
    assert any(
        "quality 'ultra' is not one of" in i.message and i.level == "error"
        for i in issues
    )


def test_quality_crf_map_has_three_presets():
    assert set(QUALITY_CRF.keys()) == {"high", "medium", "low"}
    assert QUALITY_CRF["high"] < QUALITY_CRF["medium"] < QUALITY_CRF["low"]


# ── Frame rate ────────────────────────────────────────────────────────
def test_frame_rate_default_is_source():
    assert Output().frame_rate == "source"


def test_frame_rate_fps_source_returns_none():
    # 'source' means "probe the first video" — fps() returns None so
    # the caller knows to supply frame_rate_override.
    assert Output(frame_rate="source").fps() is None


@pytest.mark.parametrize("key,expected", [
    ("24", 24),
    ("30", 30),
    ("60", 60),
])
def test_frame_rate_fps_fixed_values(key, expected):
    assert Output(frame_rate=key).fps() == expected


def test_frame_rate_roundtrip():
    o = Output(frame_rate="60")
    o2 = Output.from_dict(o.to_dict())
    assert o2.frame_rate == "60"


def test_frame_rate_keys_include_expected():
    for k in ("source", "24", "30", "60"):
        assert k in FRAME_RATE_KEYS


def test_validate_rejects_unknown_frame_rate(tmp_path: Path):
    v = _make_video(tmp_path, "a")
    p = Project(
        items=[Segment(id="s1", video=str(v))],
        output=Output(folder=str(tmp_path / "out"), frame_rate="120"),
    )
    issues = validate(p)
    assert any(
        "frame_rate '120' is not one of" in i.message and i.level == "error"
        for i in issues
    )


def test_validate_accepts_source_frame_rate(tmp_path: Path):
    v = _make_video(tmp_path, "a")
    p = Project(
        items=[Segment(id="s1", video=str(v))],
        output=Output(folder=str(tmp_path / "out"), frame_rate="source"),
    )
    errors = [i for i in validate(p) if i.level == "error"]
    assert not any("frame_rate" in e.message for e in errors)


# ── Metadata ──────────────────────────────────────────────────────────
def test_metadata_defaults_all_none():
    md = Metadata()
    assert md.title is None
    assert md.artist is None
    assert md.date is None
    assert md.genre is None
    assert md.comment is None
    assert md.copyright is None
    assert md.non_empty_items() == []


def test_metadata_to_dict_omits_empty_fields():
    md = Metadata(title="Hello", artist="Liquid Releasing")
    d = md.to_dict()
    assert d == {"title": "Hello", "artist": "Liquid Releasing"}
    # None/empty values don't appear
    assert "date" not in d
    assert "comment" not in d


def test_metadata_roundtrip():
    md = Metadata(
        title="Wild Ride",
        artist="Liquid Releasing",
        date="2026-04-19",
        genre="Haptic",
        comment="v1.2 final cut",
        copyright="© 2026 Liquid Releasing",
    )
    md2 = Metadata.from_dict(md.to_dict())
    assert md2 == md


def test_metadata_non_empty_items_in_declared_order():
    md = Metadata(title="T", artist="A", genre="G")
    items = md.non_empty_items()
    # Preserves the authored order: title, artist, date, genre, comment, copyright
    assert items == [("title", "T"), ("artist", "A"), ("genre", "G")]


def test_output_metadata_roundtrip():
    o = Output(
        folder="/tmp/out",
        metadata=Metadata(title="My Video", artist="LR"),
    )
    o2 = Output.from_dict(o.to_dict())
    assert o2.metadata.title == "My Video"
    assert o2.metadata.artist == "LR"
    assert o2.metadata.date is None


def test_output_without_metadata_roundtrip():
    """An Output with only empty metadata should not serialize the
    metadata key (keeps existing JSON files clean)."""
    o = Output(folder="/tmp/out")
    d = o.to_dict()
    assert "metadata" not in d
    # And round-trips back to defaults
    o2 = Output.from_dict(d)
    assert o2.metadata == Metadata()


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


# ── SectionOverlay (Phase A data model) ───────────────────────────────
def test_section_overlays_default_empty():
    sec = Section(id="sec1")
    assert sec.overlays == []


def test_image_overlay_roundtrip(tmp_path: Path):
    img = tmp_path / "logo.png"
    img.write_bytes(b"")
    ov = SectionOverlay(
        id="ov1", kind="image", file=str(img),
        start_s=2.0, duration_s=5.0,
        fade_in_s=0.5, fade_out_s=0.5,
        position="br", opacity=0.8, scale_pct=50,
    )
    d = ov.to_dict()
    assert d["kind"] == "image"
    assert d["position"] == "br"
    assert d["scale_pct"] == 50
    # Audio-only field not emitted for image overlays
    assert "mix_pct" not in d
    ov2 = SectionOverlay.from_dict(d)
    assert ov2.position == "br"
    assert ov2.opacity == 0.8
    assert ov2.scale_pct == 50


def test_image_overlay_scale_default_is_100():
    ov = SectionOverlay(id="ov1", kind="image", file="x.png")
    assert ov.scale_pct == 100


def test_validate_overlay_bad_scale_pct(tmp_path: Path):
    v = _make_video(tmp_path, "a")
    img = tmp_path / "x.png"
    img.write_bytes(b"")
    sec = Section(
        id="sec1",
        segments=[Segment(id="s1", video=str(v))],
        overlays=[SectionOverlay(
            id="ov1", kind="image", file=str(img), scale_pct=500,
        )],
    )
    p = Project(
        sections=[sec], output=Output(folder=str(tmp_path / "out")),
    )
    issues = validate(p)
    assert any(
        i.level == "error" and "scale_pct must be between" in i.message
        for i in issues
    )


def test_audio_overlay_roundtrip(tmp_path: Path):
    snd = tmp_path / "bed.mp3"
    snd.write_bytes(b"")
    ov = SectionOverlay(
        id="ov2", kind="audio", file=str(snd),
        start_s=0.0, duration_s=10.0,
        fade_in_s=1.0, fade_out_s=2.0,
        mix_pct=35,
    )
    d = ov.to_dict()
    assert d["kind"] == "audio"
    assert d["mix_pct"] == 35
    # Image-only fields not emitted for audio overlays
    assert "position" not in d
    assert "opacity" not in d
    ov2 = SectionOverlay.from_dict(d)
    assert ov2.mix_pct == 35


def test_section_overlays_project_roundtrip(tmp_path: Path):
    v = _make_video(tmp_path, "a")
    img = tmp_path / "bug.png"
    img.write_bytes(b"")
    sec = Section(
        id="sec1",
        segments=[Segment(id="s1", video=str(v))],
        overlays=[SectionOverlay(
            id="ov1", kind="image", file=str(img),
            start_s=1.0, duration_s=3.0, position="tl",
        )],
    )
    p = Project(sections=[sec])
    path = tmp_path / "p.json"
    p.save(path)
    loaded = Project.load(path)
    assert len(loaded.sections[0].overlays) == 1
    assert loaded.sections[0].overlays[0].kind == "image"
    assert loaded.sections[0].overlays[0].position == "tl"


def test_section_overlays_omitted_when_empty(tmp_path: Path):
    """Sections with no overlays shouldn't write an `overlays` key —
    keeps JSON clean for the common no-overlay case."""
    v = _make_video(tmp_path, "a")
    sec = Section(id="sec1", segments=[Segment(id="s1", video=str(v))])
    d = sec.to_dict()
    assert "overlays" not in d


def test_validate_overlay_missing_file_warns(tmp_path: Path):
    v = _make_video(tmp_path, "a")
    sec = Section(
        id="sec1",
        segments=[Segment(id="s1", video=str(v))],
        overlays=[SectionOverlay(
            id="ov1", kind="image",
            file=str(tmp_path / "nope.png"),
        )],
    )
    p = Project(
        sections=[sec],
        output=Output(folder=str(tmp_path / "out")),
    )
    issues = validate(p)
    assert any(
        i.level == "warning" and "Overlay file not found" in i.message
        for i in issues
    )


def test_validate_overlay_bad_position(tmp_path: Path):
    v = _make_video(tmp_path, "a")
    img = tmp_path / "x.png"
    img.write_bytes(b"")
    sec = Section(
        id="sec1",
        segments=[Segment(id="s1", video=str(v))],
        overlays=[SectionOverlay(
            id="ov1", kind="image", file=str(img),
            position="middle",  # type: ignore[arg-type]
        )],
    )
    p = Project(
        sections=[sec], output=Output(folder=str(tmp_path / "out")),
    )
    issues = validate(p)
    assert any(
        i.level == "error" and "position 'middle'" in i.message
        for i in issues
    )


def test_validate_overlay_bad_opacity(tmp_path: Path):
    v = _make_video(tmp_path, "a")
    img = tmp_path / "x.png"
    img.write_bytes(b"")
    sec = Section(
        id="sec1",
        segments=[Segment(id="s1", video=str(v))],
        overlays=[SectionOverlay(
            id="ov1", kind="image", file=str(img), opacity=1.5,
        )],
    )
    p = Project(
        sections=[sec], output=Output(folder=str(tmp_path / "out")),
    )
    issues = validate(p)
    assert any(
        i.level == "error" and "opacity must be between" in i.message
        for i in issues
    )


def test_validate_overlay_bad_mix_pct(tmp_path: Path):
    v = _make_video(tmp_path, "a")
    snd = tmp_path / "x.mp3"
    snd.write_bytes(b"")
    sec = Section(
        id="sec1",
        segments=[Segment(id="s1", video=str(v))],
        overlays=[SectionOverlay(
            id="ov1", kind="audio", file=str(snd), mix_pct=150,
        )],
    )
    p = Project(
        sections=[sec], output=Output(folder=str(tmp_path / "out")),
    )
    issues = validate(p)
    assert any(
        i.level == "error" and "mix_pct must be between" in i.message
        for i in issues
    )


def test_validate_overlay_negative_times(tmp_path: Path):
    v = _make_video(tmp_path, "a")
    img = tmp_path / "x.png"
    img.write_bytes(b"")
    sec = Section(
        id="sec1",
        segments=[Segment(id="s1", video=str(v))],
        overlays=[SectionOverlay(
            id="ov1", kind="image", file=str(img),
            start_s=-1.0, duration_s=-2.0,
        )],
    )
    p = Project(
        sections=[sec], output=Output(folder=str(tmp_path / "out")),
    )
    issues = validate(p)
    assert any("start_s must be non-negative" in i.message for i in issues)
    assert any("duration_s must be non-negative" in i.message for i in issues)


def test_output_channels_from_dict_defaults_match_the_dataclass():
    """An omitted key must not silently disable a channel. `from_dict`
    used to default everything but `main` to False while the dataclass
    defaulted them True, so a hand-written or partial project file lost
    channels it never asked to lose."""
    partial = OutputChannels.from_dict({"main": True})
    assert partial.to_dict() == OutputChannels().to_dict()
    # An EXPLICIT false is still honoured -- these are vetoes.
    vetoed = OutputChannels.from_dict({"three_phase_estim": False})
    assert vetoed.three_phase_estim is False
    assert vetoed.main is True


def test_validate_rejects_an_offset_masquerading_as_kelvin(tmp_path: Path):
    """color_temperature_k is ABSOLUTE Kelvin. An offset written here
    ("+500 warmer" -> 500) is outside ffmpeg's 1000..40000 range and
    aborts the whole video render at filter-graph setup, so say so
    before the forge starts rather than 40 minutes into it."""
    v1 = _make_video(tmp_path, "a")
    p = Project(items=[Segment(id="s1", video=str(v1), color_temperature_k=500)])
    issues = validate(p)
    assert any("color_temperature_k" in i.message and i.level == "error"
               for i in issues)


def test_validate_accepts_a_real_kelvin_value(tmp_path: Path):
    v1 = _make_video(tmp_path, "a")
    p = Project(items=[Segment(id="s1", video=str(v1), color_temperature_k=7000)])
    assert not any("color_temperature_k" in i.message for i in validate(p))

