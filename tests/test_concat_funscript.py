# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Unit tests for funscript concatenation."""

from __future__ import annotations

import json
from pathlib import Path

from forgeassembler_core.concat_funscript import (
    FunscriptPart,
    channels_for_segment,
    concat_funscripts,
    detected_channels,
    forge_funscripts,
)
from forgeassembler_core.layout import lay_out
from forgeassembler_core.project import (
    AudioLayer,
    Joiner,
    Output,
    OutputChannels,
    Project,
    Segment,
)


def _fs(*pairs: tuple[int, int]) -> dict:
    return {"actions": [{"at": a, "pos": p} for a, p in pairs]}


def test_shift_timestamps_by_offset():
    a = _fs((0, 0), (100, 50), (200, 100))
    b = _fs((0, 100), (50, 0))
    result = concat_funscripts([
        FunscriptPart(a, duration_ms=300),
        FunscriptPart(b, duration_ms=100),
    ])
    assert result["actions"] == [
        {"at": 0, "pos": 0},
        {"at": 100, "pos": 50},
        {"at": 200, "pos": 100},
        {"at": 300, "pos": 100},
        {"at": 350, "pos": 0},
    ]


def test_empty_middle_part_still_advances_offset():
    a = _fs((0, 0), (50, 100))
    b = _fs((0, 50))
    result = concat_funscripts([
        FunscriptPart(a, duration_ms=100),
        FunscriptPart({"actions": []}, duration_ms=200),  # joiner gap
        FunscriptPart(b, duration_ms=50),
    ])
    assert result["actions"] == [
        {"at": 0, "pos": 0},
        {"at": 50, "pos": 100},
        {"at": 300, "pos": 50},
    ]


def test_chapters_recorded():
    a = _fs((0, 0))
    b = _fs((0, 100))
    result = concat_funscripts([
        FunscriptPart(a, duration_ms=1000, chapter_name="Intro"),
        FunscriptPart(b, duration_ms=500, chapter_name="Scene 1"),
    ])
    assert result["chapters"] == [
        {"name": "Intro", "startTime": 0, "endTime": 1000},
        {"name": "Scene 1", "startTime": 1000, "endTime": 1500},
    ]


def test_no_chapters_when_none_supplied():
    result = concat_funscripts([
        FunscriptPart(_fs((0, 0)), duration_ms=100),
    ])
    assert "chapters" not in result


def test_input_actions_sorted_in_output():
    # If a part was out of order, concat's final sort should still
    # yield monotonic timestamps.
    a = {"actions": [{"at": 100, "pos": 50}, {"at": 0, "pos": 0}]}
    result = concat_funscripts([FunscriptPart(a, duration_ms=200)])
    ts = [act["at"] for act in result["actions"]]
    assert ts == sorted(ts)


# ── forge_funscripts (project → files) ────────────────────────────────
def _write_funscript(path: Path, *pairs: tuple[int, int]) -> None:
    path.write_text(
        json.dumps({"actions": [{"at": a, "pos": p} for a, p in pairs]}),
        encoding="utf-8",
    )


def _make_clip(folder: Path, stem: str, main_pairs, **channel_pairs):
    """Write a dummy mp4 + a main funscript + arbitrary channel scripts."""
    folder.mkdir(parents=True, exist_ok=True)
    video = folder / f"{stem}.mp4"
    video.write_bytes(b"")
    _write_funscript(folder / f"{stem}.funscript", *main_pairs)
    for channel, pairs in channel_pairs.items():
        _write_funscript(folder / f"{stem}.{channel}.funscript", *pairs)
    return video


def test_forge_funscripts_writes_main_channel(tmp_path: Path):
    video = _make_clip(
        tmp_path / "clip1", "c1",
        [(0, 0), (100, 50), (200, 100)],
    )
    out_folder = tmp_path / "out"
    p = Project(
        items=[Segment(id="s1", video=str(video))],
        output=Output(folder=str(out_folder), basename="combined"),
        output_channels=OutputChannels(main=True),
    )
    layout = lay_out(p, probe=lambda _p: 300)
    written = forge_funscripts(p, layout)
    assert len(written) == 1
    assert written[0] == out_folder / "combined.funscript"
    assert written[0].is_file()
    data = json.loads(written[0].read_text(encoding="utf-8"))
    assert data["actions"] == [
        {"at": 0, "pos": 0},
        {"at": 100, "pos": 50},
        {"at": 200, "pos": 100},
    ]


def test_forge_funscripts_shifts_timestamps_across_segments(tmp_path: Path):
    v1 = _make_clip(tmp_path / "one", "a", [(0, 0), (500, 100)])
    v2 = _make_clip(tmp_path / "two", "b", [(0, 0), (250, 100)])
    out_folder = tmp_path / "out"
    p = Project(
        items=[
            Segment(id="s1", video=str(v1)),
            Segment(id="s2", video=str(v2)),
        ],
        output=Output(folder=str(out_folder), basename="combined"),
        output_channels=OutputChannels(main=True),
    )
    # seg 1 = 1000ms, seg 2 = 500ms → seg 2 actions shift by 1000
    probe_map = {str(v1): 1000, str(v2): 500}
    layout = lay_out(p, probe=lambda pth: probe_map[str(pth)])
    written = forge_funscripts(p, layout)
    assert len(written) == 1
    data = json.loads(written[0].read_text(encoding="utf-8"))
    assert data["actions"] == [
        {"at": 0, "pos": 0},
        {"at": 500, "pos": 100},
        {"at": 1000, "pos": 0},
        {"at": 1250, "pos": 100},
    ]


def test_forge_funscripts_multi_axis_emits_one_file_per_axis(tmp_path: Path):
    video = _make_clip(
        tmp_path / "mx", "clip",
        [(0, 0)],
        pitch=[(0, 10), (100, 90)],
        roll=[(0, 20)],
    )
    out_folder = tmp_path / "out"
    p = Project(
        items=[Segment(id="s1", video=str(video))],
        output=Output(folder=str(out_folder), basename="out"),
        output_channels=OutputChannels(main=True, multi_axis=True),
    )
    layout = lay_out(p, probe=lambda _p: 200)
    written = forge_funscripts(p, layout)
    names = sorted(p.name for p in written)
    # main + pitch + roll (others skipped because no actions)
    assert names == ["out.funscript", "out.pitch.funscript", "out.roll.funscript"]


def test_forge_funscripts_joiner_gap_advances_offset(tmp_path: Path):
    v1 = _make_clip(tmp_path / "a", "a", [(0, 0), (100, 100)])
    v2 = _make_clip(tmp_path / "b", "b", [(0, 0)])
    out_folder = tmp_path / "out"
    p = Project(
        items=[
            Segment(id="s1", video=str(v1)),
            Joiner(id="j1", joiner_type="fade_to_black",
                   params={"duration_s": 2.0}),
            Segment(id="s2", video=str(v2)),
        ],
        output=Output(folder=str(out_folder), basename="out"),
        output_channels=OutputChannels(main=True),
    )
    # Segments both 1000ms; joiner 2000ms; seg 2 should shift by 3000
    probe_map = {str(v1): 1000, str(v2): 1000}
    layout = lay_out(p, probe=lambda pth: probe_map[str(pth)])
    written = forge_funscripts(p, layout)
    data = json.loads(written[0].read_text(encoding="utf-8"))
    assert {"at": 3000, "pos": 0} in data["actions"]


def test_forge_funscripts_source_none_contributes_gap(tmp_path: Path):
    """A segment marked 'none' contributes no actions but still takes
    its duration (so subsequent actions shift correctly)."""
    v1 = _make_clip(tmp_path / "a", "a", [(0, 0), (100, 100)])
    v2 = _make_clip(tmp_path / "b", "b", [(0, 50)])
    out_folder = tmp_path / "out"
    p = Project(
        items=[
            Segment(id="s1", video=str(v1), funscripts_source="none"),
            Segment(id="s2", video=str(v2)),
        ],
        output=Output(folder=str(out_folder), basename="out"),
        output_channels=OutputChannels(main=True),
    )
    probe_map = {str(v1): 500, str(v2): 500}
    layout = lay_out(p, probe=lambda pth: probe_map[str(pth)])
    written = forge_funscripts(p, layout)
    data = json.loads(written[0].read_text(encoding="utf-8"))
    # Only seg 2's action, shifted by seg 1's 500ms
    assert data["actions"] == [{"at": 500, "pos": 50}]


def test_forge_funscripts_explicit_path_wins(tmp_path: Path):
    """funscripts_source='explicit' uses the explicit dict, not the
    video's siblings."""
    video = _make_clip(tmp_path / "c", "clip", [(0, 0)])  # has sibling
    custom = tmp_path / "custom.funscript"
    _write_funscript(custom, (0, 77))
    out_folder = tmp_path / "out"
    p = Project(
        items=[Segment(
            id="s1", video=str(video),
            funscripts_source="explicit",
            explicit_funscripts={"main": str(custom)},
        )],
        output=Output(folder=str(out_folder), basename="out"),
        output_channels=OutputChannels(main=True),
    )
    layout = lay_out(p, probe=lambda _p: 1000)
    written = forge_funscripts(p, layout)
    data = json.loads(written[0].read_text(encoding="utf-8"))
    assert data["actions"] == [{"at": 0, "pos": 77}]


def test_forge_funscripts_skips_empty_channels(tmp_path: Path):
    """Channel with no actions in any segment → no file written."""
    video = _make_clip(tmp_path / "c", "clip", [(0, 50)])
    out_folder = tmp_path / "out"
    p = Project(
        items=[Segment(id="s1", video=str(video))],
        output=Output(folder=str(out_folder), basename="out"),
        # Turn on three_phase even though no alpha/beta scripts exist
        output_channels=OutputChannels(main=True, three_phase_estim=True),
    )
    layout = lay_out(p, probe=lambda _p: 1000)
    written = forge_funscripts(p, layout)
    names = sorted(p.name for p in written)
    # Only main gets written; alpha / beta are silent
    assert names == ["out.funscript"]


def test_forge_funscripts_still_image_contributes_gap(tmp_path: Path):
    """PNG title segments never carry funscripts but their duration
    still shifts subsequent action timestamps."""
    v = _make_clip(tmp_path / "v", "v", [(0, 10)])
    png = tmp_path / "title.png"
    png.write_bytes(b"")
    out_folder = tmp_path / "out"
    p = Project(
        items=[
            Segment(id="s1", video=str(png), still_duration_s=2.0),
            Segment(id="s2", video=str(v)),
        ],
        output=Output(folder=str(out_folder), basename="out"),
        output_channels=OutputChannels(main=True),
    )
    layout = lay_out(p, probe=lambda _p: 500)
    written = forge_funscripts(p, layout)
    data = json.loads(written[0].read_text(encoding="utf-8"))
    # PNG = 2000ms → v's action at 0 shifts to 2000
    assert data["actions"] == [{"at": 2000, "pos": 10}]


def test_forge_funscripts_returns_empty_when_no_channel_selected(tmp_path: Path):
    video = _make_clip(tmp_path / "c", "clip", [(0, 10)])
    out_folder = tmp_path / "out"
    p = Project(
        items=[Segment(id="s1", video=str(video))],
        output=Output(folder=str(out_folder), basename="out"),
        output_channels=OutputChannels(main=False),  # nothing on
    )
    layout = lay_out(p, probe=lambda _p: 100)
    written = forge_funscripts(p, layout)
    assert written == []


def test_forge_funscripts_bookmarks_become_chapters(tmp_path: Path):
    video = _make_clip(tmp_path / "c", "clip", [(0, 10)])
    out_folder = tmp_path / "out"
    p = Project(
        items=[Segment(id="s1", video=str(video), bookmark="Intro")],
        output=Output(folder=str(out_folder), basename="out"),
        output_channels=OutputChannels(main=True),
    )
    layout = lay_out(p, probe=lambda _p: 1000)
    written = forge_funscripts(p, layout)
    data = json.loads(written[0].read_text(encoding="utf-8"))
    assert data["chapters"] == [
        {"name": "Intro", "startTime": 0, "endTime": 1000},
    ]


# ── detection-driven channel selection ────────────────────────────────
# A real FunscriptForge scene ships ~20 channels: the 10 we have
# categories for plus device/parameter tracks (handy, shaker, volume,
# frequency, pulse_rise_time, ...). The allow-list these tests replaced
# dropped every uncategorised one on the floor.

def test_forge_writes_uncategorised_device_channels(tmp_path: Path):
    """`handy` / `volume` are in no OutputChannels group, and still forge."""
    video = _make_clip(
        tmp_path / "c", "clip", [(0, 10)],
        handy=[(0, 20)], volume=[(0, 30)], pulse_rise_time=[(0, 40)],
    )
    out_folder = tmp_path / "out"
    p = Project(
        items=[Segment(id="s1", video=str(video))],
        output=Output(folder=str(out_folder), basename="out"),
    )
    layout = lay_out(p, probe=lambda _p: 100)
    names = {w.name for w in forge_funscripts(p, layout)
             if w.suffix == ".funscript"}
    assert names == {
        "out.funscript", "out.handy.funscript",
        "out.volume.funscript", "out.pulse_rise_time.funscript",
    }


def test_forge_skips_a_vetoed_group_but_keeps_the_rest(tmp_path: Path):
    """OutputChannels subtracts from detection; it never adds to it."""
    video = _make_clip(
        tmp_path / "c", "clip", [(0, 10)],
        alpha=[(0, 20)], beta=[(0, 30)], pitch=[(0, 40)], shaker=[(0, 50)],
    )
    out_folder = tmp_path / "out"
    p = Project(
        items=[Segment(id="s1", video=str(video))],
        output=Output(folder=str(out_folder), basename="out"),
        output_channels=OutputChannels(three_phase_estim=False),
    )
    layout = lay_out(p, probe=lambda _p: 100)
    names = {w.name for w in forge_funscripts(p, layout)
             if w.suffix == ".funscript"}
    assert "out.alpha.funscript" not in names
    assert "out.beta.funscript" not in names
    assert names == {
        "out.funscript", "out.pitch.funscript", "out.shaker.funscript",
    }


def test_forge_never_writes_a_channel_no_clip_carries(tmp_path: Path):
    """Every group is ON by default; only DETECTED channels get files."""
    video = _make_clip(tmp_path / "c", "clip", [(0, 10)], alpha=[(0, 20)])
    out_folder = tmp_path / "out"
    p = Project(
        items=[Segment(id="s1", video=str(video))],
        output=Output(folder=str(out_folder), basename="out"),
        output_channels=OutputChannels(),  # all vetoes off == everything on
    )
    layout = lay_out(p, probe=lambda _p: 100)
    names = {w.name for w in forge_funscripts(p, layout)
             if w.suffix == ".funscript"}
    assert names == {"out.funscript", "out.alpha.funscript"}


def test_detected_channels_unions_across_clips(tmp_path: Path):
    """Two clips of differing capability -> the union is forged, and the
    clip that lacks a channel contributes a silent gap of its length."""
    v1 = _make_clip(tmp_path / "a", "a", [(0, 10)], twist=[(0, 90)])
    v2 = _make_clip(tmp_path / "b", "b", [(0, 10)], handy=[(0, 70)])
    out_folder = tmp_path / "out"
    p = Project(
        items=[Segment(id="s1", video=str(v1)), Segment(id="s2", video=str(v2))],
        output=Output(folder=str(out_folder), basename="out"),
    )
    assert detected_channels(p) == {"main", "twist", "handy"}
    layout = lay_out(p, probe=lambda _p: 1000)
    written = {w.name: w for w in forge_funscripts(p, layout)
               if w.suffix == ".funscript"}
    assert set(written) == {
        "out.funscript", "out.twist.funscript", "out.handy.funscript",
    }
    # `handy` only exists on the SECOND clip, so its action lands after
    # the first clip's full 1000ms -- the gap is preserved, not closed up.
    handy = json.loads(written["out.handy.funscript"].read_text(encoding="utf-8"))
    assert handy["actions"] == [{"at": 1000, "pos": 70}]


def test_channels_for_segment_reads_an_explicit_map(tmp_path: Path):
    """A `.forge` import arrives as funscripts_source='explicit'."""
    seg = Segment(
        id="s1", video=str(tmp_path / "v.mp4"),
        funscripts_source="explicit",
        explicit_funscripts={
            "main": str(tmp_path / "v.funscript"),
            "shaker": str(tmp_path / "v.shaker.funscript"),
            "empty": "",
        },
    )
    assert channels_for_segment(seg) == {"main", "shaker"}


def test_channels_for_segment_is_empty_for_a_still(tmp_path: Path):
    seg = Segment(id="s1", video=str(tmp_path / "card.png"), still_duration_s=3)
    assert channels_for_segment(seg) == set()


def test_funscript_chapters_match_the_mp4s(tmp_path: Path):
    """The video takes chapters from `build_chapters` (one per SECTION);
    the funscript used to mark one per bookmarked SEGMENT. A two-clip,
    one-section compilation therefore shipped 2 chapters in the funscript
    and 1 in the MP4 — same forge, different navigation."""
    from forgeassembler_core.chapters import build_chapters
    from forgeassembler_core.project import Section

    v1 = _make_clip(tmp_path / "a", "a", [(0, 10)])
    v2 = _make_clip(tmp_path / "b", "b", [(0, 20)])
    out_folder = tmp_path / "out"
    p = Project(
        sections=[Section(id="sec1", segments=[
            Segment(id="s1", video=str(v1), bookmark="One"),
            Segment(id="s2", video=str(v2), bookmark="Two"),
        ])],
        output=Output(folder=str(out_folder), basename="out"),
    )
    layout = lay_out(p, probe=lambda _p: 1000)
    written = forge_funscripts(p, layout)
    data = json.loads(written[0].read_text(encoding="utf-8"))

    expected = [
        {"name": c.name, "startTime": c.start_ms, "endTime": c.end_ms}
        for c in build_chapters(p, layout)
    ]
    assert data["chapters"] == expected
    assert len(data["chapters"]) == 1  # one section == one chapter


def test_each_section_becomes_a_funscript_chapter(tmp_path: Path):
    """Two sections -> two chapters, in both outputs."""
    from forgeassembler_core.project import Section
    v1 = _make_clip(tmp_path / "a", "a", [(0, 10)])
    v2 = _make_clip(tmp_path / "b", "b", [(0, 20)])
    out_folder = tmp_path / "out"
    p = Project(
        sections=[
            Section(id="sec1", segments=[Segment(id="s1", video=str(v1), bookmark="One")]),
            Section(id="sec2", segments=[Segment(id="s2", video=str(v2), bookmark="Two")]),
        ],
        output=Output(folder=str(out_folder), basename="out"),
    )
    layout = lay_out(p, probe=lambda _p: 1000)
    data = json.loads(forge_funscripts(p, layout)[0].read_text(encoding="utf-8"))
    assert [c["name"] for c in data["chapters"]] == ["One", "Two"]
    assert data["chapters"][1]["startTime"] == 1000

