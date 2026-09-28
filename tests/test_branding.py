# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Optional studio branding at each end of a compilation.

Branding is a `.forge` scene like any other, imported into a Segment — so it
brings its own audio AND its own funscripts. That is the point of the intro:
it plays before any content, which makes it usable to calibrate a device.

It belongs to no Section, which is what keeps it out of the chapter list while
still pushing chapter 01 later by its own length.
"""

from __future__ import annotations

from pathlib import Path

from forgeassembler_core.chapters import build_chapters
from forgeassembler_core.concat_funscript import detected_channels
from forgeassembler_core.layout import lay_out
from forgeassembler_core.project import (
    Joiner,
    Output,
    Project,
    Section,
    Segment,
    validate,
)


def _seg(sid: str, path: Path, **kw) -> Segment:
    path.write_bytes(b"")
    return Segment(id=sid, video=str(path), **kw)


def _project(tmp_path: Path) -> Project:
    return Project(
        sections=[
            Section(id="sec1", name="One",
                    segments=[_seg("a", tmp_path / "a.mp4")]),
            Section(id="sec2", name="Two",
                    segments=[_seg("b", tmp_path / "b.mp4")]),
        ],
        output=Output(folder=str(tmp_path / "out"), basename="Comp"),
    )


# ── ordering ─────────────────────────────────────────────────────────
def test_branding_brackets_the_whole_compilation(tmp_path):
    p = _project(tmp_path)
    p.output.branding_intro = _seg("intro", tmp_path / "intro.mp4")
    p.output.branding_outro = _seg("outro", tmp_path / "outro.mp4")
    assert [i.id for i in p.items] == ["intro", "a", "b", "outro"]


def test_branding_plays_before_the_compilations_own_title_page(tmp_path):
    """Studio bumper, then the title naming this compilation -- the cinema
    order. It also puts the intro's calibration funscripts at absolute zero."""
    p = _project(tmp_path)
    p.output.branding_intro = _seg("intro", tmp_path / "intro.mp4")
    p.output.opening_joiner = Joiner(id="join-open", joiner_type="title_card")
    assert [i.id for i in p.items][:2] == ["intro", "join-open"]


def test_either_end_is_optional(tmp_path):
    p = _project(tmp_path)
    assert [i.id for i in p.items] == ["a", "b"]
    p.output.branding_outro = _seg("outro", tmp_path / "outro.mp4")
    assert [i.id for i in p.items] == ["a", "b", "outro"]


# ── which segment list answers which question ────────────────────────
def test_content_and_timeline_are_different_questions(tmp_path):
    """`segments()` is the compilation; `timeline_segments()` is the file.

    The loudest caller of `segments()` asks "what resolution is the source?",
    and that has to follow the footage rather than a bumper that may well have
    been authored at a different size.
    """
    p = _project(tmp_path)
    p.output.branding_intro = _seg("intro", tmp_path / "intro.mp4")
    assert [s.id for s in p.segments()] == ["a", "b"]
    assert [s.id for s in p.timeline_segments()] == ["intro", "a", "b"]


def test_a_branding_only_project_still_has_no_content(tmp_path):
    p = Project(sections=[Section(id="sec1", segments=[])],
                output=Output(folder=str(tmp_path / "out")))
    p.output.branding_intro = _seg("intro", tmp_path / "intro.mp4")
    errors = [i for i in validate(p) if i.level == "error"]
    assert any("no segments" in i.message.lower() for i in errors)


# ── chapters ─────────────────────────────────────────────────────────
def test_branding_gets_no_chapter_of_its_own(tmp_path):
    p = _project(tmp_path)
    p.output.branding_intro = _seg("intro", tmp_path / "intro.mp4")
    p.output.branding_outro = _seg("outro", tmp_path / "outro.mp4")
    layout = lay_out(p, probe=lambda _p: 10_000)
    names = [c.name for c in build_chapters(p, layout)]
    assert names == ["One", "Two"]


def test_chapter_one_starts_after_the_intro(tmp_path):
    """A viewer skipping to chapter 01 lands on content, not on the bumper."""
    p = _project(tmp_path)
    layout = lay_out(p, probe=lambda _p: 10_000)
    without = build_chapters(p, layout)[0].start_ms

    p.output.branding_intro = _seg("intro", tmp_path / "intro.mp4")
    layout = lay_out(p, probe=lambda _p: 10_000)
    with_intro = build_chapters(p, layout)[0].start_ms

    assert without == 0
    assert with_intro == 10_000


# ── what branding contributes ────────────────────────────────────────
def test_a_channel_only_the_branding_has_still_gets_a_track(tmp_path):
    """The intro's funscripts are the calibration run. A channel only it
    carries must still appear in the combined output."""
    p = _project(tmp_path)
    p.output.branding_intro = _seg(
        "intro", tmp_path / "intro.mp4",
        funscripts_source="explicit",
        explicit_funscripts={"main": str(tmp_path / "i.funscript"),
                             "estim3p:alpha": str(tmp_path / "i.alpha.funscript")},
    )
    assert "estim3p:alpha" in detected_channels(p)


def test_a_missing_branding_video_fails_validation(tmp_path):
    """Before the encode, not part-way through it."""
    p = _project(tmp_path)
    p.output.branding_intro = Segment(id="intro", video=str(tmp_path / "gone.mp4"))
    errors = [i for i in validate(p) if i.level == "error"]
    assert any("gone.mp4" in i.message for i in errors)


# ── persistence ──────────────────────────────────────────────────────
def test_branding_round_trips_through_the_project_file(tmp_path):
    """It has to live in the FILE, not only in a remembered preference --
    `cli.py forge` has no access to the app's settings, so a scripted forge
    would otherwise drop the branding without saying so."""
    p = _project(tmp_path)
    p.output.branding_intro = _seg("intro", tmp_path / "intro.mp4")
    path = tmp_path / "p.forgeproject"
    p.save(path)
    again = Project.load(path)
    assert again.output.branding_intro is not None
    assert again.output.branding_intro.video.endswith("intro.mp4")
    assert again.output.branding_outro is None


def test_a_project_without_branding_writes_no_branding_keys(tmp_path):
    """Every project that predates the feature round-trips byte-identically."""
    d = _project(tmp_path).output.to_dict()
    assert "branding_intro" not in d
    assert "branding_outro" not in d
