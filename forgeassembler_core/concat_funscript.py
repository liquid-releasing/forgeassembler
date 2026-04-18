# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Funscript concatenation: shift timestamps, merge actions, add chapters."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

__all__ = [
    "FunscriptPart",
    "concat_funscripts",
    "read_funscript",
    "write_funscript",
]


@dataclass
class FunscriptPart:
    """One segment's contribution to the combined funscript."""
    funscript: dict             # parsed JSON {"actions": [...], ...}
    duration_ms: int            # how long this part occupies in the output
    chapter_name: str | None = None  # bookmark label for this segment


def read_funscript(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Funscript is not a JSON object: {path}")
    data.setdefault("actions", [])
    return data


def write_funscript(path: str | Path, funscript: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(funscript, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def concat_funscripts(parts: Iterable[FunscriptPart]) -> dict:
    """Concatenate N funscripts into one.

    Each part's actions get their `at` timestamps shifted by the running
    offset. Chapters are accumulated as `{"name", "startTime", "endTime"}`
    entries (ms).

    Joiner gaps: if a part has no funscript but occupies time, pass a
    FunscriptPart with an empty funscript (`{"actions": []}`) and the
    desired duration. V1 policy is "hold last position" — we do not
    insert synthetic actions; the player will hold between actions
    naturally.
    """
    out_actions: list[dict] = []
    chapters: list[dict] = []
    offset_ms = 0

    for part in parts:
        actions = part.funscript.get("actions") or []
        for a in actions:
            out_actions.append({
                "at": int(a["at"]) + offset_ms,
                "pos": int(a["pos"]),
            })
        if part.chapter_name:
            chapters.append({
                "name": part.chapter_name,
                "startTime": offset_ms,
                "endTime": offset_ms + part.duration_ms,
            })
        offset_ms += part.duration_ms

    # Stable sort in case input wasn't strictly sorted
    out_actions.sort(key=lambda a: a["at"])

    out: dict = {"actions": out_actions}
    if chapters:
        out["chapters"] = chapters
    return out
