# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Unit tests for the chapters module + ffmpeg-command integration."""

from __future__ import annotations

from pathlib import Path

from forgeassembler_core.chapters import (
    Chapter,
    build_chapters,
    write_ffmetadata,
)
from forgeassembler_core.concat_video import build_ffmpeg_command
from forgeassembler_core.layout import lay_out
from forgeassembler_core.project import (
    Joiner,
    Output,
    Project,
    Segment,
)


def _mp4(tmp: Path, name: str) -> Path:
    p = tmp / f"{name}.mp4"
    p.write_bytes(b"")
    return p


def _project(tmp: Path, *items, **overrides) -> Project:
    defaults = {"folder": str(tmp / "out"), "frame_rate": "30"}
    defaults.update(overrides)
    return Project(items=list(items), output=Output(**defaults))


# ── build_chapters ────────────────────────────────────────────────────
def test_build_chapters_single_segment_uses_full_duration(tmp_path: Path):
    v = _mp4(tmp_path, "clip")
    p = _project(tmp_path, Segment(id="s1", video=str(v)))
    layout = lay_out(p, probe=lambda _p: 5000)
    chapters = build_chapters(p, layout)
    assert chapters == [Chapter(name="clip", start_ms=0, end_ms=5000)]


def test_build_chapters_uses_bookmark_when_set(tmp_path: Path):
    v = _mp4(tmp_path, "clip")
    p = _project(tmp_path, Segment(
        id="s1", video=str(v), bookmark="Opening Scene",
    ))
    layout = lay_out(p, probe=lambda _p: 3000)
    chapters = build_chapters(p, layout)
    assert chapters[0].name == "Opening Scene"


def test_build_chapters_falls_back_to_filename_stem(tmp_path: Path):
    v = _mp4(tmp_path, "victoriaoats_07")
    p = _project(tmp_path, Segment(id="s1", video=str(v)))
    layout = lay_out(p, probe=lambda _p: 1000)
    chapters = build_chapters(p, layout)
    assert chapters[0].name == "victoriaoats_07"


def test_build_chapters_multiple_segments_contiguous(tmp_path: Path):
    v1 = _mp4(tmp_path, "a")
    v2 = _mp4(tmp_path, "b")
    v3 = _mp4(tmp_path, "c")
    p = _project(
        tmp_path,
        Segment(id="s1", video=str(v1)),
        Segment(id="s2", video=str(v2)),
        Segment(id="s3", video=str(v3)),
    )
    probe_map = {str(v1): 1000, str(v2): 2000, str(v3): 3000}
    layout = lay_out(p, probe=lambda pth: probe_map[str(pth)])
    chapters = build_chapters(p, layout)
    # Contiguous: each chapter starts where the previous ended
    assert chapters == [
        Chapter(name="a", start_ms=0,    end_ms=1000),
        Chapter(name="b", start_ms=1000, end_ms=3000),
        Chapter(name="c", start_ms=3000, end_ms=6000),
    ]


def test_build_chapters_joiner_time_absorbed_into_preceding_chapter(tmp_path: Path):
    """A fade_to_black joiner between two segments should extend the
    preceding chapter's end to the start of the next segment."""
    v1 = _mp4(tmp_path, "a")
    v2 = _mp4(tmp_path, "b")
    p = _project(
        tmp_path,
        Segment(id="s1", video=str(v1)),
        Joiner(id="j1", joiner_type="fade_to_black",
               params={"duration_s": 2.0}),
        Segment(id="s2", video=str(v2)),
    )
    layout = lay_out(p, probe=lambda _p: 1000)
    chapters = build_chapters(p, layout)
    # seg1 covers 0-1000ms; joiner adds 2000ms; seg2 starts at 3000ms.
    # Chapter 'a' extends from 0 to 3000 (absorbing the transition).
    assert chapters[0] == Chapter(name="a", start_ms=0, end_ms=3000)
    assert chapters[1] == Chapter(name="b", start_ms=3000, end_ms=4000)


def test_build_chapters_includes_still_image_segments(tmp_path: Path):
    """PNG title-card segments get their own chapter."""
    v = _mp4(tmp_path, "clip")
    png = tmp_path / "intro.png"
    png.write_bytes(b"")
    p = _project(
        tmp_path,
        Segment(id="s1", video=str(png), still_duration_s=3.0,
                bookmark="Intro"),
        Segment(id="s2", video=str(v)),
    )
    layout = lay_out(p, probe=lambda _p: 1000)
    chapters = build_chapters(p, layout)
    assert len(chapters) == 2
    assert chapters[0].name == "Intro"
    assert chapters[0].start_ms == 0
    assert chapters[0].end_ms == 3000


def test_build_chapters_empty_project_returns_empty(tmp_path: Path):
    p = _project(tmp_path)
    layout = lay_out(p, probe=lambda _p: 0)
    assert build_chapters(p, layout) == []


def test_build_chapters_empty_bookmark_falls_back_to_stem(tmp_path: Path):
    v = _mp4(tmp_path, "fallback")
    p = _project(tmp_path, Segment(
        id="s1", video=str(v), bookmark="   ",  # whitespace only
    ))
    layout = lay_out(p, probe=lambda _p: 1000)
    chapters = build_chapters(p, layout)
    assert chapters[0].name == "fallback"


# ── write_ffmetadata ──────────────────────────────────────────────────
def test_write_ffmetadata_has_header(tmp_path: Path):
    out = tmp_path / "ch.txt"
    write_ffmetadata([Chapter(name="A", start_ms=0, end_ms=1000)], out)
    contents = out.read_text(encoding="utf-8")
    assert contents.startswith(";FFMETADATA1")


def test_write_ffmetadata_formats_one_chapter(tmp_path: Path):
    out = tmp_path / "ch.txt"
    write_ffmetadata(
        [Chapter(name="Intro", start_ms=0, end_ms=5000)], out,
    )
    contents = out.read_text(encoding="utf-8")
    assert "[CHAPTER]" in contents
    assert "TIMEBASE=1/1000" in contents
    assert "START=0" in contents
    assert "END=5000" in contents
    assert "title=Intro" in contents


def test_write_ffmetadata_multiple_chapters(tmp_path: Path):
    out = tmp_path / "ch.txt"
    write_ffmetadata([
        Chapter(name="One", start_ms=0, end_ms=1000),
        Chapter(name="Two", start_ms=1000, end_ms=2000),
    ], out)
    contents = out.read_text(encoding="utf-8")
    # Two [CHAPTER] blocks
    assert contents.count("[CHAPTER]") == 2
    assert "title=One" in contents
    assert "title=Two" in contents


def test_write_ffmetadata_escapes_special_chars(tmp_path: Path):
    """= ; # and \\ need to be backslash-escaped inside key=value lines."""
    out = tmp_path / "ch.txt"
    write_ffmetadata([Chapter(
        name="A=B;C#D\\E", start_ms=0, end_ms=1000,
    )], out)
    contents = out.read_text(encoding="utf-8")
    # Each special char should appear escaped
    assert "A\\=B\\;C\\#D\\\\E" in contents


def test_write_ffmetadata_creates_parent_dir(tmp_path: Path):
    out = tmp_path / "nested" / "deeper" / "ch.txt"
    write_ffmetadata([Chapter(name="A", start_ms=0, end_ms=1)], out)
    assert out.is_file()


# ── build_ffmpeg_command integration ──────────────────────────────────
def test_build_ffmpeg_command_without_chapters_no_map_metadata(tmp_path: Path):
    v = _mp4(tmp_path, "a")
    p = _project(tmp_path, Segment(id="s1", video=str(v)))
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout)
    assert "-map_metadata" not in cmd.output_args


def test_build_ffmpeg_command_with_chapters_adds_input_and_map(tmp_path: Path):
    v = _mp4(tmp_path, "a")
    ch = tmp_path / "chapters.txt"
    ch.write_text(";FFMETADATA1\n", encoding="utf-8")
    p = _project(tmp_path, Segment(id="s1", video=str(v)))
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout, chapters_path=str(ch))

    # Chapters input is added with -f ffmetadata pre_args
    assert any(
        inp.path == str(ch) and inp.pre_args == ["-f", "ffmetadata"]
        for inp in cmd.inputs
    )
    # -map_metadata points at the chapters input's index
    assert "-map_metadata" in cmd.output_args
    idx = cmd.output_args.index("-map_metadata")
    chapters_input_idx = next(
        i for i, inp in enumerate(cmd.inputs) if inp.path == str(ch)
    )
    assert cmd.output_args[idx + 1] == str(chapters_input_idx)


def test_build_ffmpeg_command_chapters_before_user_metadata(tmp_path: Path):
    """`-map_metadata` must come BEFORE `-metadata key=value` so per-key
    overrides win when they collide with chapter file globals."""
    from forgeassembler_core.project import Metadata
    v = _mp4(tmp_path, "a")
    ch = tmp_path / "chapters.txt"
    ch.write_text(";FFMETADATA1\n", encoding="utf-8")
    p = _project(
        tmp_path,
        Segment(id="s1", video=str(v)),
        metadata=Metadata(title="Custom Title"),
    )
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout, chapters_path=str(ch))
    args = cmd.output_args
    map_idx = args.index("-map_metadata")
    # Find the first -metadata arg (title=...)
    meta_idx = next(i for i, a in enumerate(args) if a == "-metadata")
    assert map_idx < meta_idx


def test_build_ffmpeg_command_chapters_to_argv_renders_input(tmp_path: Path):
    v = _mp4(tmp_path, "a")
    ch = tmp_path / "chapters.txt"
    ch.write_text(";FFMETADATA1\n", encoding="utf-8")
    p = _project(tmp_path, Segment(id="s1", video=str(v)))
    layout = lay_out(p, probe=lambda _p: 1000)
    cmd = build_ffmpeg_command(p, layout, chapters_path=str(ch))
    argv = cmd.to_argv("ffmpeg")
    # argv contains both `-f ffmetadata` and the chapters path after -i
    assert "ffmetadata" in argv
    assert str(ch) in argv
