# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""The video is published atomically: the final name means a finished render.

`forge_video` encodes to `<stem>.tmp.<pid>.mp4` and `os.replace`s it into
place. Without this, ffmpeg's `-y` truncates the previous render on its
first frame and writes the real name for the whole encode -- so anything
that stops the run part-way (a cancel, a crash, a power cut) leaves a
partial file that is indistinguishable from a finished one, with the good
render it replaced already gone.

These tests fake ffmpeg. The engine is exercised for real up to the
subprocess boundary; only the encode itself is stubbed.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from forgeassembler_core import concat_video
from forgeassembler_core.concat_video import forge_video
from forgeassembler_core.layout import lay_out
from forgeassembler_core.project import Output, Project, Section, Segment


def _project(tmp_path: Path) -> Project:
    src = tmp_path / "clip.mp4"
    src.write_bytes(b"")
    return Project(
        sections=[Section(id="sec1", name="One",
                          segments=[Segment(id="a", video=str(src))])],
        output=Output(folder=str(tmp_path / "out"), basename="Comp",
                      frame_rate="30", resolution="1080p"),
    )


class _FakeProc:
    """Stands in for ffmpeg. Writes whatever argv says to write."""

    def __init__(self, argv, returncode=0, write=True):
        self.argv = list(argv)
        self.returncode = returncode
        self.written = Path(self.argv[-1])
        if write:
            self.written.write_bytes(b"fresh encode")
        self.stdout = iter(["frame=1 time=00:00:01.00", "frame=2"])

    def wait(self):
        return self.returncode


@pytest.fixture
def spy(monkeypatch):
    """Fake ffmpeg; records the argv it was handed. `rc` flips the exit."""
    seen: dict = {"argv": None, "rc": 0, "write": True}

    def fake_popen(argv, **_kw):
        seen["argv"] = list(argv)
        return _FakeProc(argv, returncode=seen["rc"], write=seen["write"])

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    # Probing the encoder shells a real ffmpeg; the choice is irrelevant here.
    monkeypatch.setattr(concat_video, "resolve_video_encoder", lambda _e: "libx264")
    monkeypatch.setattr(concat_video, "_resolve_ffmpeg_exe", lambda: "ffmpeg")
    return seen


def _forge(project: Project) -> Path:
    layout = lay_out(project, probe=lambda _p: 10_000)
    return forge_video(project, layout)


# ── what ffmpeg is actually told to write ────────────────────────────
def test_ffmpeg_writes_a_temp_never_the_final_name(tmp_path, spy):
    p = _project(tmp_path)
    out = _forge(p)

    target = Path(spy["argv"][-1])
    assert target != out
    assert target.name == f"{out.stem}.tmp.{os.getpid()}{out.suffix}"
    assert target.parent == out.parent, "temp must be a SIBLING -- os.replace is only atomic within one volume"


def test_the_temp_keeps_the_extension(tmp_path, spy):
    """ffmpeg chooses its muxer from the extension. A temp called `.tmp`
    would make it guess, or refuse."""
    _forge(_project(tmp_path))
    assert Path(spy["argv"][-1]).suffix == ".mp4"


# ── success ──────────────────────────────────────────────────────────
def test_a_finished_forge_publishes_the_final_name(tmp_path, spy):
    out = _forge(_project(tmp_path))
    assert out.exists()
    assert out.read_bytes() == b"fresh encode"
    assert list(out.parent.glob("*.tmp.*")) == []


def test_the_published_name_still_carries_the_render_tag(tmp_path, spy):
    """The temp round-trip must not cost the `.1080p30` naming that lets
    two renders of one project coexist."""
    out = _forge(_project(tmp_path))
    assert out.name == "Comp.1080p30.mp4"


# ── failure: the whole point ─────────────────────────────────────────
def test_a_failed_encode_leaves_the_previous_render_untouched(tmp_path, spy):
    p = _project(tmp_path)
    good = Path(p.output.folder) / "Comp.1080p30.mp4"
    good.parent.mkdir(parents=True, exist_ok=True)
    good.write_bytes(b"the render from last night")

    spy["rc"] = 1
    with pytest.raises(RuntimeError):
        _forge(p)

    assert good.read_bytes() == b"the render from last night"


def test_a_failed_encode_removes_its_own_temp(tmp_path, spy):
    p = _project(tmp_path)
    spy["rc"] = 1
    with pytest.raises(RuntimeError):
        _forge(p)
    assert list((Path(p.output.folder)).glob("*.tmp.*")) == []


def test_a_failed_encode_still_reports_ffmpegs_own_words(tmp_path, spy):
    """Cleaning up must not swallow the diagnosis."""
    p = _project(tmp_path)
    spy["rc"] = 1
    with pytest.raises(RuntimeError, match="ffmpeg exited with code 1"):
        _forge(p)


# ── what a hard kill leaves behind ───────────────────────────────────
def test_a_temp_from_a_killed_run_is_swept(tmp_path, spy):
    """`taskkill /T /F` never runs our cleanup, so the next forge does it.
    A 4K feature's worth of abandoned bytes is worth reclaiming."""
    p = _project(tmp_path)
    folder = Path(p.output.folder)
    folder.mkdir(parents=True, exist_ok=True)
    orphan = folder / "Comp.1080p30.tmp.999999.mp4"
    orphan.write_bytes(b"half an encode")

    _forge(p)

    assert not orphan.exists()


def test_the_sweep_spares_the_finished_renders_beside_it(tmp_path, spy):
    p = _project(tmp_path)
    folder = Path(p.output.folder)
    folder.mkdir(parents=True, exist_ok=True)
    keep = folder / "Comp.4k30.mp4"
    keep.write_bytes(b"the 4K one I am keeping")

    _forge(p)

    assert keep.read_bytes() == b"the 4K one I am keeping"
