# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Tests for importing a FunscriptForge `.forge` bundle as a Segment.

Two layers:
  • a synthetic bundle built in tmp_path — deterministic, exercises the full
    manifest parse + multi-channel (motion + estim + tcode) station mapping +
    relink + cache idempotency + the `.forge`-dir collision guard;
  • the real motion-only VictoriaOaks_stingy.forge produced by
    `scripts/make_forge_fixture.ps1` (skipped if absent) — confirms the actual
    FunscriptForge export round-trips through the importer.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from forgeassembler_core.forge_bundle import (
    ForgeBundle,
    detect_forge_bundle,
    forge_bundle_to_segment,
    is_forge_bundle,
)

REPO = Path(__file__).resolve().parents[1]
REAL_BUNDLE = REPO / "test_media" / "forge_bundles" / "VictoriaOaks_stingy.forge"
FULL_BUNDLE = REPO / "test_media" / "forge_bundles" / "VictoriaOaks_stingy.full.forge"


# ── synthetic bundle helpers ─────────────────────────────────────────
def _write_bundle(path: Path, manifest: dict, files: dict[str, str]) -> Path:
    """Zip up a `.forge` bundle: manifest.ffmeta + the given relpath->content."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.ffmeta", json.dumps(manifest, indent=2))
        for rel, content in files.items():
            z.writestr(rel, content)
    return path


def _fake_funscript(n: int = 3) -> str:
    actions = [{"at": i * 100, "pos": (i * 7) % 100} for i in range(n)]
    return json.dumps({"actions": actions})


def _multichannel_manifest(stem: str = "Scene") -> dict:
    return {
        "version": 1, "schema": "ffmeta/v1", "stem": stem,
        "created_with": "FunscriptForge", "duration_ms": 123456,
        "project_id": "abc123", "project_version": 2,
        "artifacts": [
            {"path": "motion.funscript", "kind": "funscript", "role": "stroke", "axis": "L0"},
            {"path": "thumbnails/funscript.png", "kind": "thumbnail", "role": "funscript"},
            {"path": f"stations/estim3p/{stem}.alpha.funscript", "kind": "funscript", "role": "estim"},
            {"path": f"stations/estim3p/{stem}.beta.funscript", "kind": "funscript", "role": "estim"},
            {"path": f"stations/estim3p/{stem}.pulse_frequency.funscript", "kind": "funscript", "role": "estim"},
            {"path": f"stations/estim3p/{stem}.alpha-prostate.funscript", "kind": "funscript", "role": "estim"},
            {"path": f"stations/tcode/{stem}.surge.funscript", "kind": "funscript", "role": "stroke", "axis": "L1"},
            {"path": f"stations/tcode/{stem}.twist.funscript", "kind": "funscript", "role": "stroke", "axis": "R2"},
        ],
        "stations": {"estim3p": {"files": []}, "tcode": {"files": []}},
    }


@pytest.fixture
def multichannel_bundle(tmp_path) -> Path:
    stem = "Scene"
    manifest = _multichannel_manifest(stem)
    files = {a["path"]: (_fake_funscript() if a["kind"] == "funscript" else "PNG")
             for a in manifest["artifacts"]}
    return _write_bundle(tmp_path / f"{stem}.forge", manifest, files)


# ── is_forge_bundle: the collision guard ─────────────────────────────
def test_is_forge_bundle_true_for_zip(multichannel_bundle):
    assert is_forge_bundle(multichannel_bundle) is True


def test_is_forge_bundle_false_for_directory(tmp_path):
    # The forgeassembler working-folder TREE is a `.forge` directory — must not
    # be mistaken for a bundle.
    d = tmp_path / "proj.forge"
    (d / "0").mkdir(parents=True)
    assert is_forge_bundle(d) is False


def test_is_forge_bundle_false_for_legacy_json_descriptor(tmp_path):
    # The old FunscriptForge `.forge` project descriptor is a JSON file, not a
    # zip — not a bundle.
    p = tmp_path / "old.forge"
    p.write_text('{"name": "legacy", "version": "1"}', encoding="utf-8")
    assert is_forge_bundle(p) is False


# ── detect_forge_bundle: parse + channel mapping ─────────────────────
def test_detect_maps_motion_and_stations(multichannel_bundle, tmp_path):
    b = detect_forge_bundle(multichannel_bundle, cache_root=tmp_path / "cache")
    assert isinstance(b, ForgeBundle)
    assert b.stem == "Scene"
    assert b.duration_ms == 123456
    assert b.project_id == "abc123"
    assert b.project_version == 2
    # motion -> main; station files -> their channel suffix.
    assert set(b.channels) == {
        "main", "alpha", "beta", "pulse_frequency", "alpha-prostate", "surge", "twist",
    }
    # paths point inside the extraction cache and exist.
    assert b.funscripts["main"].name == "motion.funscript"
    assert b.funscripts["surge"].is_file()
    assert b.funscripts["alpha-prostate"].is_file()


def test_detect_ignores_thumbnails(multichannel_bundle, tmp_path):
    b = detect_forge_bundle(multichannel_bundle, cache_root=tmp_path / "cache")
    assert all("thumbnail" not in ch for ch in b.channels)
    # 7 funscript artifacts, 1 thumbnail ignored.
    assert len(b.funscripts) == 7


def test_detect_is_idempotent(multichannel_bundle, tmp_path):
    cache = tmp_path / "cache"
    b1 = detect_forge_bundle(multichannel_bundle, cache_root=cache)
    mtime = (b1.cache_dir / "manifest.ffmeta").stat().st_mtime
    b2 = detect_forge_bundle(multichannel_bundle, cache_root=cache)
    assert b1.cache_dir == b2.cache_dir
    # second call reused the extraction (manifest not rewritten).
    assert (b2.cache_dir / "manifest.ffmeta").stat().st_mtime == mtime


def test_detect_rejects_non_bundle(tmp_path):
    p = tmp_path / "notazip.forge"
    p.write_text("nope", encoding="utf-8")
    with pytest.raises(ValueError):
        detect_forge_bundle(p)


# ── relink → Segment ─────────────────────────────────────────────────
def test_to_segment_with_relinked_video(multichannel_bundle, tmp_path):
    b = detect_forge_bundle(multichannel_bundle, cache_root=tmp_path / "cache")
    seg = forge_bundle_to_segment(b, video="C:/clips/scene.mp4")
    assert seg.video == "C:/clips/scene.mp4"
    assert seg.funscripts_source == "explicit"
    assert seg.bookmark == "Scene"
    assert seg.explicit_funscripts["main"].endswith("motion.funscript")
    assert "surge" in seg.explicit_funscripts
    # round-trips through the project schema as an explicit-funscript segment.
    d = seg.to_dict()
    assert d["funscripts"]["source"] == "explicit"
    assert set(d["funscripts"]["files"]) == set(b.channels)


def test_to_segment_without_video_raises(multichannel_bundle, tmp_path):
    b = detect_forge_bundle(multichannel_bundle, cache_root=tmp_path / "cache")
    assert b.media_path is None  # lean synthetic bundle has no media
    with pytest.raises(ValueError, match="no resolvable video"):
        forge_bundle_to_segment(b)


# ── bundled media resolution ─────────────────────────────────────────
def test_bundled_media_resolves(tmp_path):
    stem = "WithMedia"
    manifest = _multichannel_manifest(stem)
    manifest["media"] = {"filename": "src.mp4", "path": "media/src.mp4", "bundled": True}
    files = {a["path"]: (_fake_funscript() if a["kind"] == "funscript" else "PNG")
             for a in manifest["artifacts"]}
    files["media/src.mp4"] = "FAKEVIDEOBYTES"
    bundle = _write_bundle(tmp_path / f"{stem}.forge", manifest, files)

    b = detect_forge_bundle(bundle, cache_root=tmp_path / "cache")
    assert b.media_path is not None
    assert b.media_path.name == "src.mp4"
    # now relink is automatic — no explicit video needed.
    seg = forge_bundle_to_segment(b)
    assert seg.video.endswith("src.mp4")


def test_media_resolved_next_to_bundle_by_filename(tmp_path):
    stem = "Relink"
    manifest = _multichannel_manifest(stem)
    # original on disk next to the bundle, matched by filename + size.
    original = tmp_path / "original.mp4"
    original.write_text("VIDEO", encoding="utf-8")
    manifest["media"] = {"filename": "original.mp4", "size": original.stat().st_size, "bundled": False}
    files = {a["path"]: _fake_funscript() for a in manifest["artifacts"] if a["kind"] == "funscript"}
    bundle = _write_bundle(tmp_path / f"{stem}.forge", manifest, files)

    b = detect_forge_bundle(bundle, cache_root=tmp_path / "cache")
    assert b.media_path == original.resolve() or b.media_path == original


# ── the real FunscriptForge export (motion-only) ─────────────────────
@pytest.mark.skipif(not REAL_BUNDLE.is_file(),
                    reason="run scripts/make_forge_fixture.ps1 to produce the real bundle")
def test_real_victoriaoaks_motion_only_bundle(tmp_path):
    b = detect_forge_bundle(REAL_BUNDLE, cache_root=tmp_path / "cache")
    assert b.stem == "VictoriaOaks_stingy"
    assert b.manifest.get("created_with") == "FunscriptForge"
    assert b.manifest.get("schema") == "ffmeta/v1"
    # this particular export was motion-only (sparse working folder).
    assert "main" in b.funscripts
    assert b.funscripts["main"].is_file()
    assert b.media_path is None  # lean export, no media
    # can't build a segment without relinking a video.
    with pytest.raises(ValueError):
        forge_bundle_to_segment(b)
    seg = forge_bundle_to_segment(b, video="C:/clips/VictoriaOaks.mp4")
    assert seg.explicit_funscripts["main"].endswith("motion.funscript")


@pytest.mark.skipif(not FULL_BUNDLE.is_file(),
                    reason="run scripts/build_forge_from_loose.py to produce the full bundle")
def test_real_victoriaoaks_full_multichannel_bundle(tmp_path):
    # Genuine FunscriptForge e-stim channels repackaged into the bundle schema.
    b = detect_forge_bundle(FULL_BUNDLE, cache_root=tmp_path / "cache")
    assert b.stem == "VictoriaOaks_stingy"
    # main + the full 14-channel e-stim set (e1..e4, alpha/beta + prostate,
    # frequency, pulse_*, volume + prostate).
    assert "main" in b.channels
    for ch in ("e1", "e2", "e3", "e4", "alpha", "beta",
               "alpha-prostate", "beta-prostate",
               "frequency", "pulse_frequency", "pulse_width", "pulse_rise_time",
               "volume", "volume-prostate"):
        assert ch in b.channels, f"missing channel {ch}"
        assert b.funscripts[ch].is_file()
    seg = forge_bundle_to_segment(b, video="C:/clips/VictoriaOaks.mp4")
    assert seg.funscripts_source == "explicit"
    assert len(seg.explicit_funscripts) == len(b.channels) == 15
