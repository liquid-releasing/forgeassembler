# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Tests for reading back what a forge wrote.

The Viewer's whole value is that it does not re-derive anything — it reports
the files on disk. So these tests build real output trees (both layouts the
forge writes) and assert what comes back out.
"""

from __future__ import annotations

import json
import zipfile

import pytest

from forgeassembler_core.viewer import (
    STROKE_DEVICE,
    load_output,
    load_single_channel,
    resolve_source,
)


def _funscript(path, actions):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"actions": actions}), encoding="utf-8")


def _ramp(n=10, step=100):
    return [{"at": i * step, "pos": 10 if i % 2 else 90} for i in range(n)]


@pytest.fixture
def folder_output(tmp_path):
    """The loose layout: stroke at the top, one folder per station."""
    out = tmp_path / "out"
    _funscript(out / "Comp.funscript", _ramp())
    _funscript(out / "E-Stim" / "Comp.alpha.funscript", _ramp())
    _funscript(out / "E-Stim" / "Comp.beta.funscript", _ramp())
    _funscript(out / "MultiFunPlayer" / "Comp.surge.funscript", _ramp())
    (out / "Comp.mp4").write_bytes(b"not really an mp4")
    return out


# ── resolving what the user opened ───────────────────────────────────
def test_resolve_accepts_the_video_the_folder_and_the_project(folder_output):
    """All three are things a person might reasonably double-click."""
    for opened in (folder_output,
                   folder_output / "Comp.mp4",
                   folder_output / "Comp.funscript"):
        kind, src, stem = resolve_source(str(opened))
        assert (kind, stem) == ("folder", "Comp")
        assert src == folder_output


def test_resolve_prefers_the_bundle_over_the_loose_folder(folder_output):
    """The bundle is the richer artifact and the one that travels."""
    (folder_output / "Comp.forge").write_bytes(b"PK\x03\x04stub")
    kind, src, stem = resolve_source(str(folder_output / "Comp.mp4"))
    assert kind == "forge"
    assert src.name == "Comp.forge"


def test_resolve_reads_a_dotted_project_name(tmp_path):
    """`.forgeproject` is the last extension, so a stem may carry dots of its
    own — `Best of.v2` must not become a stem of `Best of`."""
    (tmp_path / "Best of.v2.forgeproject").write_text("{}", encoding="utf-8")
    _funscript(tmp_path / "Best of.v2.funscript", _ramp())
    kind, src, stem = resolve_source(str(tmp_path))
    assert stem == "Best of.v2"


def test_resolve_returns_none_for_a_path_that_is_not_there(tmp_path):
    assert resolve_source(str(tmp_path / "nope.mp4")) is None


# ── the stem is the OUTPUT's name, not the project's ─────────────────
# Measured against a real 2h 4K forge: the folder held
# `its-just-ai-sex.forgeproject` beside `It's Just AI Sex.4k30.mp4`,
# `It's Just AI Sex.forge` and `It's Just AI Sex.funscript`. Trusting the
# project file made the Viewer hunt under a name nothing on disk used, so
# it found no video, no chapters and no bundle.
def test_the_project_file_does_not_get_to_name_the_output(tmp_path):
    """`output.basename` and the project's filename are separate fields."""
    (tmp_path / "its-just-ai-sex.forgeproject").write_text("{}", encoding="utf-8")
    _funscript(tmp_path / "It's Just AI Sex.funscript", _ramp())
    kind, src, stem = resolve_source(str(tmp_path))
    assert stem == "It's Just AI Sex"


def test_the_bundle_outranks_the_project_file(tmp_path):
    (tmp_path / "renamed-project.forgeproject").write_text("{}", encoding="utf-8")
    (tmp_path / "Best Of.forge").write_bytes(b"PK\x03\x04stub")
    kind, src, stem = resolve_source(str(tmp_path))
    assert (kind, stem) == ("forge", "Best Of")


def test_a_video_stem_gives_up_its_render_tag(tmp_path):
    """`Best Of.4k30.mp4` belongs to the stem `Best Of` -- that is what the
    funscripts and sidecars beside it are called."""
    (tmp_path / "Best Of.4k30.mp4").write_bytes(b"x")
    kind, src, stem = resolve_source(str(tmp_path))
    assert stem == "Best Of"


def test_a_stem_that_merely_looks_tagged_is_left_alone(tmp_path):
    """`.part2` is not a render tag. Only a size label welded to a frame
    rate is, so nothing else may be trimmed off a user's filename."""
    (tmp_path / "Best Of.part2.mp4").write_bytes(b"x")
    kind, src, stem = resolve_source(str(tmp_path))
    assert stem == "Best Of.part2"


# ── finding the render to play ───────────────────────────────────────
def test_the_monitor_finds_a_tagged_render(folder_output):
    """Renders carry their size now, so the untagged name is often absent."""
    (folder_output / "Comp.mp4").unlink()
    (folder_output / "Comp.4k30.mp4").write_bytes(b"x")
    assert load_output(str(folder_output))["mediaPath"].endswith("Comp.4k30.mp4")


def test_an_untagged_render_still_wins(folder_output):
    """What an older forge wrote, and what a hand-renamed file looks like."""
    (folder_output / "Comp.1080p30.mp4").write_bytes(b"x")
    assert load_output(str(folder_output))["mediaPath"].endswith("Comp.mp4")


def test_the_newest_rendition_is_the_one_offered(folder_output):
    """Several coexist by design; the Viewer exists to check the one you
    just made."""
    import os
    import time
    (folder_output / "Comp.mp4").unlink()
    old = folder_output / "Comp.1080p30.mp4"
    new = folder_output / "Comp.4k30.mp4"
    old.write_bytes(b"x")
    new.write_bytes(b"x")
    now = time.time()
    os.utime(old, (now - 5000, now - 5000))
    os.utime(new, (now, now))
    assert load_output(str(folder_output))["mediaPath"].endswith("Comp.4k30.mp4")


def test_a_half_written_temp_is_never_offered_as_the_render(folder_output):
    """`Comp.4k30.tmp.10344.mp4` is a forge still running. Handing it to the
    monitor would play a truncated file and look like a broken render."""
    (folder_output / "Comp.mp4").unlink()
    (folder_output / "Comp.4k30.tmp.10344.mp4").write_bytes(b"half")
    assert load_output(str(folder_output))["mediaPath"] is None


# ── the loose folder layout ──────────────────────────────────────────
def test_folder_output_groups_channels_by_device(folder_output):
    res = load_output(str(folder_output))
    assert res["available"] is True
    names = [d["name"] for d in res["devices"]]
    # Stroke first: it is the track every device derives from.
    assert names == [STROKE_DEVICE, "E-Stim", "MultiFunPlayer"]
    estim = next(d for d in res["devices"] if d["name"] == "E-Stim")
    assert [c["name"] for c in estim["channels"]] == ["alpha", "beta"]


def test_folder_output_finds_the_video_for_the_monitor(folder_output):
    res = load_output(str(folder_output))
    assert res["mediaPath"].endswith("Comp.mp4")


def test_duration_comes_from_the_last_action(folder_output):
    res = load_output(str(folder_output))
    assert res["durationMs"] == 900


def test_thumbnail_and_audio_folders_are_not_devices(folder_output):
    """`thumbnails/` and `audio/` are output, not stations — and a device with
    no funscripts in it must not appear as an empty picker entry."""
    (folder_output / "thumbnails").mkdir()
    (folder_output / "thumbnails" / "hero.png").write_bytes(b"x")
    (folder_output / "audio").mkdir()
    (folder_output / "Empty Device").mkdir()
    names = [d["name"] for d in load_output(str(folder_output))["devices"]]
    assert "thumbnails" not in names
    assert "audio" not in names
    assert "Empty Device" not in names


def test_a_one_action_channel_is_dropped(tmp_path):
    """One point is not a curve; drawing it claims a lane exists that has
    nothing in it."""
    out = tmp_path / "out"
    _funscript(out / "S.funscript", _ramp())
    _funscript(out / "E-Stim" / "S.alpha.funscript", [{"at": 0, "pos": 50}])
    names = [d["name"] for d in load_output(str(out))["devices"]]
    assert names == [STROKE_DEVICE]


def test_nothing_forged_yet_is_reported_not_raised(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "Comp.mp4").write_bytes(b"x")
    res = load_output(str(out))
    assert res["available"] is False
    assert res["devices"] == []
    assert "error" in res


# ── the .forge bundle ────────────────────────────────────────────────
@pytest.fixture
def bundle_output(tmp_path):
    # A distinct folder from `folder_output`, so one test can take both.
    out = tmp_path / "packed"
    out.mkdir()
    bundle = out / "Comp.forge"
    with zipfile.ZipFile(bundle, "w") as z:
        z.writestr("motion.funscript", json.dumps({"actions": _ramp()}))
        z.writestr("stations/estim3p/Comp.alpha.funscript",
                   json.dumps({"actions": _ramp()}))
        # A station's own stroke track keeps the suffix-less spelling.
        z.writestr("stations/tcode/Comp.funscript", json.dumps({"actions": _ramp()}))
        z.writestr("chapters.json", json.dumps({
            "chapters": [
                {"at_ms": 0, "end_ms": 500, "name": "One"},
                {"at_ms": 500, "end_ms": 900, "name": "Two"},
            ],
        }))
        z.writestr("beats.json", json.dumps({"bpm": 120, "beats_ms": [0, 500]}))
        z.writestr("audio.json", json.dumps(
            {"peaks": [0.1] * 100, "duration_ms": 900, "hop_ms": 9}))
    (out / "Comp.mp4").write_bytes(b"x")
    return out


def test_bundle_maps_station_ids_to_names_people_recognise(bundle_output):
    """`estim3p` means nothing in a device picker; `E-Stim` does."""
    res = load_output(str(bundle_output / "Comp.forge"))
    names = [d["name"] for d in res["devices"]]
    assert names == [STROKE_DEVICE, "E-Stim", "MultiFunPlayer"]


def test_bundle_station_own_stroke_track_is_named_main(bundle_output):
    res = load_output(str(bundle_output / "Comp.forge"))
    mfp = next(d for d in res["devices"] if d["name"] == "MultiFunPlayer")
    assert [c["name"] for c in mfp["channels"]] == ["main"]


def test_bundle_carries_the_context_lanes(bundle_output):
    res = load_output(str(bundle_output / "Comp.forge"))
    assert [c["name"] for c in res["chapters"]] == ["One", "Two"]
    assert res["beats"]["bpm"] == 120
    assert res["audio"]["peaks"]


def test_audio_hop_is_rederived_after_decimation(bundle_output):
    """The stored `hop_ms` describes samples that decimation removed. Carrying
    it through would draw the waveform at the wrong time scale."""
    res = load_output(str(bundle_output / "Comp.forge"), audio_points=10)
    audio = res["audio"]
    assert len(audio["peaks"]) <= 10
    assert audio["hopMs"] == pytest.approx(900 / len(audio["peaks"]))


def test_an_unreadable_bundle_reports_rather_than_raises(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "Comp.forge").write_bytes(b"this is not a zip")
    res = load_output(str(out / "Comp.forge"))
    assert res["available"] is False


# ── decimation ───────────────────────────────────────────────────────
def test_the_timeline_keeps_the_extremes_it_decimates_past(tmp_path):
    """Peak-preserving is the whole contract: a spike that a stride would land
    between must survive, because a spike is what the Viewer is looking for."""
    out = tmp_path / "out"
    acts = [{"at": i * 10, "pos": 50} for i in range(1000)]
    acts[501] = {"at": 5010, "pos": 100}
    acts[503] = {"at": 5030, "pos": 0}
    _funscript(out / "S.funscript", acts)
    res = load_output(str(out), max_points=40)
    got = res["devices"][0]["channels"][0]["actions"]
    assert len(got) <= 40
    assert max(a["pos"] for a in got) == 100
    assert min(a["pos"] for a in got) == 0


def test_the_monitor_gets_a_curve_that_moves_forward_in_time(tmp_path):
    """The timeline's min/max envelope emits low+high PAIRS per bin, which read
    as a zigzag once the monitor zooms in. The monitor's thinning must stay
    monotonic in time."""
    out = tmp_path / "out"
    _funscript(out / "S.funscript", _ramp(n=5000, step=10))
    res = load_single_channel(str(out), STROKE_DEVICE, "main", cap=100)
    ats = [a["at"] for a in res["actions"]]
    assert res["available"] is True
    assert len(ats) <= 101
    assert ats == sorted(ats)
    assert ats[-1] == 49990  # the real last sample, never dropped


def test_monitor_reads_a_station_channel_from_each_layout(folder_output, bundle_output):
    loose = load_single_channel(str(folder_output), "E-Stim", "alpha")
    assert loose["available"] is True and loose["rawCount"] == 10

    packed = load_single_channel(str(bundle_output / "Comp.forge"), "E-Stim", "alpha")
    assert packed["available"] is True and packed["rawCount"] == 10


def test_monitor_returns_empty_rather_than_another_channel(folder_output):
    """Never substitute. A monitor that lies about which channel it is showing
    is worse than one that is briefly blank — see forgemoment's
    monitorChannel.js for the bug this mirrors."""
    res = load_single_channel(str(folder_output), "E-Stim", "no-such-channel")
    assert res["available"] is False
    assert res["actions"] == []


# ── the flat layout, which is what a real output on disk looked like ──
@pytest.fixture
def flat_output(tmp_path):
    """What forges wrote before station folders landed — and still what a
    hand-assembled set beside a video looks like."""
    out = tmp_path / "flat"
    _funscript(out / "Comp.funscript", _ramp())
    for chan in ("alpha", "beta", "volume", "frequency"):
        _funscript(out / f"Comp.{chan}.funscript", _ramp())
    _funscript(out / "Comp.handy.funscript", _ramp())
    _funscript(out / "Comp.twist.funscript", _ramp())
    (out / "Comp.mp4").write_bytes(b"x")
    return out


def test_flat_channels_are_attributed_the_way_the_forge_attributes_them(flat_output):
    """Measured against a real September output: reading only the station
    FOLDERS found 1 channel of 16. A flat `<stem>.alpha.funscript` has to
    land under the same device the foldered spelling would."""
    res = load_output(str(flat_output))
    by_name = {d["name"]: [c["name"] for c in d["channels"]] for d in res["devices"]}
    assert by_name[STROKE_DEVICE] == ["main"]
    assert by_name["E-Stim"] == ["alpha", "beta", "frequency", "volume"]
    assert by_name["Handy"] == ["handy"]
    assert by_name["MultiFunPlayer"] == ["twist"]


def test_a_channel_no_station_claims_sits_with_the_stroke_track(tmp_path):
    """Rather than inventing a device for it."""
    out = tmp_path / "odd"
    _funscript(out / "S.funscript", _ramp())
    _funscript(out / "S.whatever.funscript", _ramp())
    res = load_output(str(out))
    assert [d["name"] for d in res["devices"]] == [STROKE_DEVICE]
    assert [c["name"] for c in res["devices"][0]["channels"]] == ["main", "whatever"]


def test_heatmap_pngs_beside_the_funscripts_are_ignored(flat_output):
    (flat_output / "Comp.alpha.heatmap.png").write_bytes(b"x")
    (flat_output / "Comp.heatmap.png").write_bytes(b"x")
    res = load_output(str(flat_output))
    estim = next(d for d in res["devices"] if d["name"] == "E-Stim")
    assert "heatmap" not in [c["name"] for c in estim["channels"]]


def test_the_footer_names_the_output_not_the_folder_it_sits_in(flat_output):
    """A folder's name is wherever the user happened to save — `forgeassembler`
    — which says nothing about which compilation is on screen."""
    res = load_output(str(flat_output))
    assert res["sourceName"] == "Comp"


def test_monitor_reads_a_flat_channel(flat_output):
    res = load_single_channel(str(flat_output), "E-Stim", "alpha")
    assert res["available"] is True
    assert res["rawCount"] == 10


def test_a_station_main_never_falls_back_to_the_universal_track(flat_output):
    """Flat, `<stem>.funscript` is the UNIVERSAL stroke track. Serving it as
    `E-Stim/main` would put one channel's data under another channel's name,
    which is the one thing the monitor must never do — see forgemoment's
    monitorChannel.js."""
    res = load_single_channel(str(flat_output), "E-Stim", "main")
    assert res["available"] is False
    assert res["actions"] == []
