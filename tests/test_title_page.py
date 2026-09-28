# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""The compilation's own title page.

Distinct from the first section's leading joiner, which also lands at
t=0: that one is the first CHAPTER's title. With both set you get the
production's title page, then chapter one's card, then the footage.

These tests lean on `Project.items` being the single place the title
page is threaded in — everything downstream reads that list, so if it is
in there the layout, the filtergraph, chapters and the funscript offsets
all see it without being told separately.
"""

from __future__ import annotations

from forgeassembler_core.concat_video import build_ffmpeg_command
from forgeassembler_core.layout import lay_out
from forgeassembler_core.project import Project

TITLE_PAGE = {
    "id": "j-open", "joiner_type": "title_card",
    "params": {"title": "MY COMPILATION", "duration_s": 5.0, "fade_s": 1.0},
}
CHAPTER_CARD = {
    "id": "j0", "joiner_type": "title_card",
    "params": {"title": "Chapter One", "duration_s": 3.0, "fade_s": 1.0},
}


def _project(opening=None, first_joiner=None):
    output = {"folder": "out", "basename": "c"}
    if opening:
        output["opening_joiner"] = opening
    return Project.from_dict({
        "version": "2.0", "name": "t", "output": output,
        "sections": [
            {"id": "s0",
             "leading_joiner": first_joiner or {"id": "j0", "joiner_type": "none",
                                                "params": {}},
             "segments": [{"id": "seg0", "video": "v0.mp4"}]},
            {"id": "s1",
             "leading_joiner": {"id": "j1", "joiner_type": "none", "params": {}},
             "segments": [{"id": "seg1", "video": "v1.mp4"}]},
        ],
    })


def _layout(project):
    return lay_out(project, probe=lambda _p: 10000)


def test_the_title_page_comes_before_any_footage():
    layout = _layout(_project(TITLE_PAGE))
    first = layout.items[0]
    assert not first.is_segment
    assert first.item.id == "j-open"
    assert (first.start_ms, first.end_ms) == (0, 5000)
    assert layout.segments()[0].start_ms == 5000


def test_the_title_page_and_the_first_chapter_card_are_different_things():
    # The whole point of the feature: a production's title, and then the
    # first chapter's, in that order.
    layout = _layout(_project(TITLE_PAGE, CHAPTER_CARD))
    joiners = [li.item.id for li in layout.joiners()]
    assert joiners[:2] == ["j-open", "j0"]
    assert [(li.start_ms, li.end_ms) for li in layout.joiners()[:2]] \
        == [(0, 5000), (5000, 8000)]
    assert layout.segments()[0].start_ms == 8000


def test_the_title_page_lengthens_the_compilation_by_its_hold():
    plain = _layout(_project()).total_duration_ms
    titled = _layout(_project(TITLE_PAGE)).total_duration_ms
    assert titled - plain == 5000


def test_the_title_page_is_rendered_like_any_other_card():
    # It rides the same path as a section's card — a bridge with the PNG
    # composited on it — rather than a second implementation.
    project = _project(TITLE_PAGE, CHAPTER_CARD)
    layout = _layout(project)
    graph = " ".join(build_ffmpeg_command(
        project, layout, frame_rate_override=30,
        title_cards={"j-open": "open.png", "j0": "ch1.png"},
    ).to_argv("ffmpeg"))
    assert "open.png" in graph
    assert "ch1.png" in graph
    assert graph.count("overlay=") == 2


def test_a_project_without_one_is_unchanged():
    # Byte-identical round trip for every project that predates this.
    project = _project()
    assert project.output.opening_joiner.joiner_type == "none"
    assert "opening_joiner" not in project.to_dict()["output"]
    assert _layout(project).items[0].is_segment


def test_the_title_page_survives_a_round_trip():
    project = Project.from_dict(_project(TITLE_PAGE).to_dict())
    assert project.output.opening_joiner.joiner_type == "title_card"
    assert project.output.opening_joiner.params["title"] == "MY COMPILATION"
    assert _layout(project).items[0].item.id == "j-open"


def test_the_first_scene_fades_in_from_the_title_page():
    # The title page is the thing before the first scene, so it is what
    # the first scene fades in FROM — and onto its colour, not black.
    project = _project({
        "id": "j-open", "joiner_type": "title_card",
        "params": {"title": "X", "duration_s": 4.0, "fade_s": 1.0,
                   "theme": "brand"},
    })
    graph = " ".join(build_ffmpeg_command(
        project, _layout(project), frame_rate_override=30,
    ).to_argv("ffmpeg"))
    assert "fade=t=in:st=0:d=1:color=0x1a0e1e" in graph


def test_a_fade_works_as_an_opening_too():
    # Not every compilation wants words in front of it; some just want to
    # come up out of black.
    project = _project({
        "id": "j-open", "joiner_type": "fade_to_black",
        "params": {"duration_s": 2.0, "fade_s": 1.0},
    })
    layout = _layout(project)
    assert (layout.items[0].start_ms, layout.items[0].end_ms) == (0, 2000)
