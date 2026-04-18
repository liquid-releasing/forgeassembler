# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Unit tests for funscript concatenation."""

from __future__ import annotations

from forgeassembler_core.concat_funscript import FunscriptPart, concat_funscripts


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
