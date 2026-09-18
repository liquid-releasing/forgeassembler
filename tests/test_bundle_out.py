# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Tests for writing the joined compilation as a `.forge` bundle.

The bundle is `ffmeta/v1` — FunscriptForge's format, verified against a real
`cli.py export --mode forge`. The load-bearing claims are that every station
survives the write, that the analysis is joined onto the COMPILATION's
timeline rather than copied from one scene, and that our own reader can
re-open what we wrote.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from forgeassembler_core.bundle_out import (
    compilation_chapters,
    join_audio_peaks,
    join_beats,
    media_provenance,
    write_forge_bundle,
)
from forgeassembler_core.forge_bundle import detect_forge_bundle, is_forge_bundle
from forgeassembler_core.layout import lay_out
from forgeassembler_core.project import Output, Project, Section, Segment


def _funscript(path: Path, pos: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"actions": [{"at": 0, "pos": pos}]}), encoding="utf-8")
    return path


def _two_scene_project(tmp_path: Path, **output) -> tuple[Project, object]:
    """Two 1000 ms clips in two sections — so one chapter each."""
    segs = []
    for name in ("a", "b"):
        v = tmp_path / f"{name}.mp4"
        v.write_bytes(b"")
        segs.append(Segment(id=name, video=str(v)))
    project = Project(
        sections=[
            Section(id="s1", name="First", segments=[segs[0]]),
            Section(id="s2", name="Second", segments=[segs[1]]),
        ],
        output=Output(folder=str(tmp_path / "out"), basename="combined", **output),
    )
    return project, lay_out(project, probe=lambda _p: 1000)


# ── station placement ────────────────────────────────────────────────
def test_every_station_lands_at_its_ffmeta_path(tmp_path: Path):
    project, layout = _two_scene_project(tmp_path)
    src = tmp_path / "src"
    funscripts = {
        "main": _funscript(src / "main.funscript", 1),
        "estim3p:alpha": _funscript(src / "three_alpha.funscript", 10),
        "focstim:alpha": _funscript(src / "foc_alpha.funscript", 11),
        "focstim4p:e1": _funscript(src / "e1.funscript", 12),
        "tcode:main": _funscript(src / "tcode_l0.funscript", 13),
        "tcode:surge": _funscript(src / "surge.funscript", 14),
    }
    out = write_forge_bundle(
        project, layout, tmp_path / "combined.forge",
        funscripts=funscripts, now=1_700_000_000,
    )
    with zipfile.ZipFile(out) as z:
        names = set(z.namelist())
        manifest = json.loads(z.read("manifest.ffmeta"))

    assert "motion.funscript" in names
    # Two stations writing `alpha` keep two files — the whole point.
    assert "stations/estim3p/combined.alpha.funscript" in names
    assert "stations/focstim/combined.alpha.funscript" in names
    assert "stations/focstim4p/combined.e1.funscript" in names
    # A station's own L0 keeps FunscriptForge's suffix-less spelling.
    assert "stations/tcode/combined.funscript" in names
    assert "stations/tcode/combined.surge.funscript" in names

    # The manifest attributes each one, and lists each station's files.
    by_path = {a["path"]: a for a in manifest["artifacts"]}
    assert by_path["motion.funscript"]["axis"] == "L0"
    assert by_path["stations/focstim/combined.alpha.funscript"]["station"] == "focstim"
    assert set(manifest["stations"]) == {"estim3p", "focstim", "focstim4p", "tcode"}
    assert sorted(manifest["stations"]["tcode"]["files"]) == [
        "combined.funscript", "combined.surge.funscript",
    ]


def test_the_manifest_says_who_made_it_and_what_from(tmp_path: Path):
    project, layout = _two_scene_project(tmp_path)
    project.sections[0].segments[0].bookmark = "Opening scene"
    out = write_forge_bundle(project, layout, tmp_path / "c.forge", now=1_700_000_000)
    with zipfile.ZipFile(out) as z:
        manifest = json.loads(z.read("manifest.ffmeta"))

    assert manifest["schema"] == "ffmeta/v1"
    # A consumer must be able to tell a compilation from an authored scene.
    assert manifest["created_with"] == "ForgeAssembler"
    assert manifest["duration_ms"] == 2000
    assert manifest["compilation"]["sections"] == 2
    assert [s["name"] for s in manifest["compilation"]["scenes"]] == [
        "Opening scene", "b",
    ]
    assert manifest["project_version"] == 1_700_000_000


def test_the_project_id_is_stable_across_re_forges(tmp_path: Path):
    project, layout = _two_scene_project(tmp_path)
    a = write_forge_bundle(project, layout, tmp_path / "a.forge", now=1)
    b = write_forge_bundle(project, layout, tmp_path / "b.forge", now=2)
    ids = []
    for p in (a, b):
        with zipfile.ZipFile(p) as z:
            ids.append(json.loads(z.read("manifest.ffmeta"))["project_id"])
    assert ids[0] == ids[1]

    # A different compilation gets its own lineage.
    project.output.basename = "something-else"
    other = write_forge_bundle(project, layout, tmp_path / "c.forge", now=3)
    with zipfile.ZipFile(other) as z:
        assert json.loads(z.read("manifest.ffmeta"))["project_id"] != ids[0]


# ── media ────────────────────────────────────────────────────────────
def test_media_is_referenced_not_bundled_by_default(tmp_path: Path):
    project, layout = _two_scene_project(tmp_path)
    video = tmp_path / "combined.mp4"
    video.write_bytes(b"x" * 4096)
    out = write_forge_bundle(project, layout, tmp_path / "c.forge", video=video)
    with zipfile.ZipFile(out) as z:
        manifest = json.loads(z.read("manifest.ffmeta"))
        assert not [n for n in z.namelist() if n.startswith("media/")]
    assert manifest["media"]["bundled"] is False
    assert manifest["media"]["filename"] == "combined.mp4"
    assert manifest["media"]["size"] == 4096
    # The key identifies the real file, which is what makes relinking safe.
    assert manifest["media"]["head_sha256"] == media_provenance(video)["head_sha256"]


def test_media_rides_along_when_asked(tmp_path: Path):
    project, layout = _two_scene_project(tmp_path)
    video = tmp_path / "combined.mp4"
    video.write_bytes(b"x" * 2048)
    out = write_forge_bundle(project, layout, tmp_path / "c.forge",
                             video=video, include_media=True)
    with zipfile.ZipFile(out) as z:
        assert "media/combined.mp4" in z.namelist()
        manifest = json.loads(z.read("manifest.ffmeta"))
    assert manifest["media"]["bundled"] is True
    assert manifest["media"]["path"] == "media/combined.mp4"


def test_a_funscript_only_forge_writes_no_media_block(tmp_path: Path):
    # `--no-video` is a real mode; the manifest must not claim a video.
    project, layout = _two_scene_project(tmp_path, produce_video=False)
    out = write_forge_bundle(project, layout, tmp_path / "c.forge")
    with zipfile.ZipFile(out) as z:
        manifest = json.loads(z.read("manifest.ffmeta"))
    assert "media" not in manifest


# ── audio ────────────────────────────────────────────────────────────
def test_audio_is_placed_by_role_the_way_funscriptforge_names_it(tmp_path: Path):
    project, layout = _two_scene_project(tmp_path)
    folder = tmp_path / "out"
    folder.mkdir(exist_ok=True)
    written = []
    for name in ("combined.mp3", "combined.prostate.mp3", "combined.beat.mp3"):
        p = folder / name
        p.write_bytes(b"ID3")
        written.append(p)

    out = write_forge_bundle(project, layout, tmp_path / "c.forge", audio=written)
    with zipfile.ZipFile(out) as z:
        names = set(z.namelist())
        manifest = json.loads(z.read("manifest.ffmeta"))
    assert {"audio/stim.mp3", "audio/stim-prostate.mp3", "audio/beat.mp3"} <= names
    roles = {a["path"]: a["role"] for a in manifest["artifacts"] if a["kind"] == "audio"}
    assert roles == {
        "audio/stim.mp3": "estim",
        "audio/stim-prostate.mp3": "estim-prostate",
        "audio/beat.mp3": "beat",
    }


# ── the compilation's chapters ───────────────────────────────────────
def test_chapters_are_the_sections(tmp_path: Path):
    project, layout = _two_scene_project(tmp_path)
    doc = compilation_chapters(project, layout)
    assert doc["schema"] == "audio-structure"
    assert [(c["name"], c["at_ms"], c["end_ms"]) for c in doc["chapters"]] == [
        ("First", 0, 1000), ("Second", 1000, 2000),
    ]
    # Authored boundaries, not a detector's guess — and it says so.
    assert doc["auto_generated"] is False


# ── joining the analysis ─────────────────────────────────────────────
def _with_sidecars(tmp_path: Path, a_side: dict | None, b_side: dict | None,
                   **trim) -> tuple[Project, object]:
    project, layout = _two_scene_project(tmp_path)
    for seg, data, name in (
        (project.sections[0].segments[0], a_side, "a"),
        (project.sections[1].segments[0], b_side, "b"),
    ):
        if data is None:
            continue
        for kind, doc in data.items():
            p = tmp_path / f"{name}.{kind}.json"
            p.write_text(json.dumps(doc), encoding="utf-8")
            seg.sidecars[kind] = str(p)
    for k, v in trim.items():
        which, field = k.split("_", 1)
        seg = (project.sections[0] if which == "a" else project.sections[1]).segments[0]
        setattr(seg, field, v)
    return project, lay_out(project, probe=lambda _p: 1000)


def test_beats_are_shifted_onto_the_compilations_timeline(tmp_path: Path):
    beats = {"beats": {"version": "1.0", "beats_ms": [0, 250, 500, 750],
                       "downbeats_ms": [0, 500]}}
    project, layout = _with_sidecars(tmp_path, beats, beats)
    joined = join_beats(project, layout)

    # The second clip's beats land where that clip actually plays.
    assert joined["beats_ms"] == [0, 250, 500, 750, 1000, 1250, 1500, 1750]
    assert joined["downbeats_ms"] == [0, 500, 1000, 1500]
    assert joined["duration_ms"] == 2000


def test_a_trim_window_selects_which_beats_come_along(tmp_path: Path):
    beats = {"beats": {"version": "1.0", "beats_ms": [0, 250, 500, 750],
                       "downbeats_ms": []}}
    # Clip A plays only 500..1000 of its source, so its first two beats are cut
    # and the survivors rebase to the window's start.
    project, layout = _with_sidecars(
        tmp_path, beats, None, a_trim_start="00:00:00.500")
    joined = join_beats(project, layout)
    assert joined["beats_ms"] == [0, 250]


def test_no_beats_anywhere_writes_no_beats_file(tmp_path: Path):
    project, layout = _two_scene_project(tmp_path)
    assert join_beats(project, layout) is None
    out = write_forge_bundle(project, layout, tmp_path / "c.forge")
    with zipfile.ZipFile(out) as z:
        assert "beats.json" not in z.namelist()


def test_waveform_peaks_are_spliced_per_clip(tmp_path: Path):
    # 100 samples at 10ms = the clip's full 1000ms.
    a = {"audio": {"version": "1.0", "hop_ms": 10, "peaks": [0.5] * 100}}
    b = {"audio": {"version": "1.0", "hop_ms": 10, "peaks": [0.9] * 100}}
    project, layout = _with_sidecars(tmp_path, a, b)
    joined = join_audio_peaks(project, layout)

    assert joined["hop_ms"] == 10
    assert joined["duration_ms"] == 2000
    # First clip's stretch reads 0.5, second's reads 0.9 — not one value
    # smeared across the whole thing.
    assert joined["peaks"][10] == 0.5
    assert joined["peaks"][150] == 0.9


def test_a_clip_with_no_waveform_leaves_silence_not_a_hole(tmp_path: Path):
    a = {"audio": {"version": "1.0", "hop_ms": 10, "peaks": [0.5] * 100}}
    project, layout = _with_sidecars(tmp_path, a, None)
    joined = join_audio_peaks(project, layout)
    # The lane still spans the whole compilation, so a viewer's time axis is
    # right; the unknown stretch is zeros.
    assert joined["peak_count"] == 2000 // 10 + 1
    assert joined["peaks"][10] == 0.5
    assert joined["peaks"][150] == 0.0


def test_a_different_hop_is_resampled_rather_than_dropped(tmp_path: Path):
    # 20ms hop over 1000ms = 50 samples. Mixing hops must not lose the lane.
    a = {"audio": {"version": "1.0", "hop_ms": 20,
                   "peaks": [i / 50 for i in range(50)]}}
    project, layout = _with_sidecars(tmp_path, a, None)
    joined = join_audio_peaks(project, layout)
    assert joined["hop_ms"] == 10
    # 500ms into the clip is sample 25 of the source.
    assert joined["peaks"][50] == 25 / 50


# ── round trip ───────────────────────────────────────────────────────
def test_we_can_re_open_what_we_wrote(tmp_path: Path):
    """The real test of writing a format: read it back with our own reader."""
    project, layout = _two_scene_project(tmp_path)
    src = tmp_path / "src"
    funscripts = {
        "main": _funscript(src / "m.funscript", 1),
        "estim3p:alpha": _funscript(src / "a3.funscript", 10),
        "focstim:alpha": _funscript(src / "af.funscript", 11),
        "focstim4p:e1": _funscript(src / "e1.funscript", 12),
    }
    video = tmp_path / "combined.mp4"
    video.write_bytes(b"x" * 1024)
    out = write_forge_bundle(project, layout, tmp_path / "combined.forge",
                             funscripts=funscripts, video=video)

    assert is_forge_bundle(out)
    bundle = detect_forge_bundle(out, cache_root=tmp_path / "cache")
    assert set(bundle.funscripts) == set(funscripts)
    # Each station's file came back with its OWN content.
    assert json.loads(bundle.funscripts["estim3p:alpha"].read_text()) \
        ["actions"][0]["pos"] == 10
    assert json.loads(bundle.funscripts["focstim:alpha"].read_text()) \
        ["actions"][0]["pos"] == 11
    assert "chapters" in bundle.sidecars
    assert bundle.duration_ms == 2000
