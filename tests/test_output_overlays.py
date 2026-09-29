# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Overlays over the WHOLE compilation, branding included.

A Section's overlays are timed from that section and can only land inside
it. Branding belongs to no Section, so nothing could reach it -- which is
where a closing logo and a credits roll have to go.

`Output.overlays` is the same `SectionOverlay` type, timed in absolute
seconds from the start of the output. Reusing the type rather than inventing
a credits one means position, fades, opacity, colour and font all come for
free, and "two sets of credits" is just two entries.
"""

from __future__ import annotations

from pathlib import Path

from forgeassembler_core.concat_video import build_ffmpeg_command
from forgeassembler_core.layout import lay_out
from forgeassembler_core.project import (
    Output,
    Project,
    Section,
    SectionOverlay,
    Segment,
)


def _file(tmp: Path, name: str) -> str:
    p = tmp / name
    p.write_bytes(b"")
    return str(p)


def _project(tmp_path: Path, **kw) -> Project:
    return Project(
        sections=[
            Section(id="sec1", name="One",
                    segments=[Segment(id="a", video=_file(tmp_path, "a.mp4"))]),
            Section(id="sec2", name="Two",
                    segments=[Segment(id="b", video=_file(tmp_path, "b.mp4"))]),
        ],
        output=Output(folder=str(tmp_path / "out"), basename="Comp",
                      frame_rate="30", **kw),
    )


def _cmd(p: Project):
    return build_ffmpeg_command(p, lay_out(p, probe=lambda _q: 10_000))


# ── the reason this exists ───────────────────────────────────────────
def test_a_compilation_overlay_can_cover_the_closing_branding(tmp_path):
    """The whole point. A Section overlay cannot reach the outro, because
    branding belongs to no Section."""
    p = _project(tmp_path)
    p.output.branding_outro = Segment(id="outro", video=_file(tmp_path, "outro.mp4"))
    p.output.overlays = [SectionOverlay(
        id="ov", kind="image", file=_file(tmp_path, "logo.png"),
        start_s=22.0, duration_s=6.0, position="br",
    )]
    fc = _cmd(p).filter_complex
    # Total is 30s: 10 + 10 content, 10 outro. The logo sits inside the outro.
    assert "enable=" in fc
    assert "between(t,22,28)" in fc.replace(" ", "")


def test_credits_are_text_over_the_whole_output(tmp_path):
    p = _project(tmp_path)
    p.output.overlays = [SectionOverlay(
        id="ov", kind="text", file="", text="Directed by\nSomeone", text_color="#ffffff",
        start_s=15.0, duration_s=4.0, position="bc",
    )]
    fc = _cmd(p).filter_complex
    assert "drawtext" in fc


def test_two_sets_of_credits_are_just_two_entries(tmp_path):
    p = _project(tmp_path)
    p.output.overlays = [
        SectionOverlay(id="ov", kind="text", file="", text="Cast", start_s=12.0, duration_s=3.0),
        SectionOverlay(id="ov", kind="text", file="", text="Crew", start_s=15.0, duration_s=3.0),
    ]
    assert _cmd(p).filter_complex.count("drawtext") == 2


# ── it must not disturb what already worked ──────────────────────────
def test_section_overlays_still_time_from_their_own_section(tmp_path):
    """Section 2 starts at 10s, so an overlay 1s into it lands at 11s --
    unchanged by the compilation window being added alongside."""
    p = _project(tmp_path)
    p.sections[1].overlays = [SectionOverlay(
        id="ov", kind="image", file=_file(tmp_path, "logo.png"),
        start_s=1.0, duration_s=2.0,
    )]
    fc = _cmd(p).filter_complex.replace(" ", "")
    assert "between(t,11,13)" in fc


def test_both_kinds_coexist(tmp_path):
    p = _project(tmp_path)
    p.sections[0].overlays = [SectionOverlay(
        id="ov", kind="image", file=_file(tmp_path, "a.png"), start_s=0.0, duration_s=2.0)]
    p.output.overlays = [SectionOverlay(
        id="ov", kind="image", file=_file(tmp_path, "b.png"), start_s=5.0, duration_s=2.0)]
    fc = _cmd(p).filter_complex.replace(" ", "")
    assert "between(t,0,2)" in fc
    assert "between(t,5,7)" in fc


def test_a_project_with_no_compilation_overlays_is_unchanged(tmp_path):
    """The window is only added when there is something in it, so no
    existing project's filtergraph moves."""
    p = _project(tmp_path)
    before = _cmd(p).filter_complex
    p.output.overlays = []
    assert _cmd(p).filter_complex == before


# ── persistence ──────────────────────────────────────────────────────
def test_overlays_round_trip_through_the_project_file(tmp_path):
    p = _project(tmp_path)
    p.output.overlays = [SectionOverlay(
        id="ov", kind="text", file="", text="Credits", start_s=3.0, duration_s=5.0,
        text_color="#ffffff", font_size=64,
    )]
    path = tmp_path / "p.forgeproject"
    p.save(path)
    again = Project.load(path)
    assert len(again.output.overlays) == 1
    ov = again.output.overlays[0]
    assert (ov.kind, ov.text, ov.font_size) == ("text", "Credits", 64)


def test_a_project_without_them_writes_no_overlays_key(tmp_path):
    """Every project that predates the feature round-trips byte-identically."""
    assert "overlays" not in _project(tmp_path).output.to_dict()


# ── where the clock starts ───────────────────────────────────────────
# Credits belong to the bumper they sit on. Their absolute start cannot be
# written down: the total duration is only settled at forge time, once every
# clip has been probed. `anchor="outro"` measures from the closing branding.
def test_an_outro_anchored_overlay_starts_at_the_bumper(tmp_path):
    p = _project(tmp_path)
    p.output.branding_outro = Segment(id="outro", video=_file(tmp_path, "outro.mp4"))
    p.output.overlays = [SectionOverlay(
        id="ov", kind="text", file="", text="Credits",
        start_s=2.0, duration_s=4.0, anchor="outro",
    )]
    # 10 + 10 content, outro starts at 20s. 2s in means 22s absolute.
    fc = _cmd(p).filter_complex.replace(" ", "")
    assert "between(t,22,26)" in fc


def test_the_same_overlay_unanchored_starts_at_the_beginning(tmp_path):
    """The contrast that makes the setting worth having."""
    p = _project(tmp_path)
    p.output.branding_outro = Segment(id="outro", video=_file(tmp_path, "outro.mp4"))
    p.output.overlays = [SectionOverlay(
        id="ov", kind="text", file="", text="Credits",
        start_s=2.0, duration_s=4.0, anchor="start",
    )]
    assert "between(t,2,6)" in _cmd(p).filter_complex.replace(" ", "")


def test_an_outro_anchor_falls_back_when_there_is_no_bumper(tmp_path):
    """Removing the branding must not make the project refuse to forge."""
    p = _project(tmp_path)
    p.output.overlays = [SectionOverlay(
        id="ov", kind="text", file="", text="Credits",
        start_s=2.0, duration_s=4.0, anchor="outro",
    )]
    assert "between(t,2,6)" in _cmd(p).filter_complex.replace(" ", "")


def test_both_anchors_can_be_used_at_once(tmp_path):
    p = _project(tmp_path)
    p.output.branding_outro = Segment(id="outro", video=_file(tmp_path, "outro.mp4"))
    p.output.overlays = [
        SectionOverlay(id="a", kind="text", file="", text="Opening",
                       start_s=1.0, duration_s=2.0, anchor="start"),
        SectionOverlay(id="b", kind="text", file="", text="Credits",
                       start_s=1.0, duration_s=2.0, anchor="outro"),
    ]
    fc = _cmd(p).filter_complex.replace(" ", "")
    assert "between(t,1,3)" in fc
    assert "between(t,21,23)" in fc


def test_the_anchor_round_trips_and_is_omitted_when_default(tmp_path):
    p = _project(tmp_path)
    p.output.branding_outro = Segment(id="outro", video=_file(tmp_path, "outro.mp4"))
    p.output.overlays = [
        SectionOverlay(id="a", kind="text", file="", text="x", anchor="outro"),
        SectionOverlay(id="b", kind="text", file="", text="y"),
    ]
    path = tmp_path / "p.forgeproject"
    p.save(path)
    import json
    raw = json.loads(path.read_text(encoding="utf-8"))["output"]["overlays"]
    assert raw[0]["anchor"] == "outro"
    assert "anchor" not in raw[1], "default must not be written"
    assert [o.anchor for o in Project.load(path).output.overlays] == ["outro", "start"]
