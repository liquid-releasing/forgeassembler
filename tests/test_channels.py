# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Tests for station-qualified channel keys and the two output layouts.

The keys exist because a channel NAME stopped identifying a file: `estim3p`,
`focstim` and `focstim4p` all write `alpha`. The layouts exist because a flat
`<stem>.alpha.funscript` cannot hold three of them — so each station's
channels go in that device's folder, exactly as a FunscriptForge loose export
writes them.
"""

from __future__ import annotations

from forgeassembler_core.channels import (
    bundle_relpath,
    channel_of,
    funscript_relpath,
    make_key,
    parse_key,
    station_folder,
    station_of,
)


def test_a_bare_channel_round_trips_unqualified():
    assert make_key(None, "alpha") == "alpha"
    assert make_key("", "alpha") == "alpha"
    assert parse_key("alpha") == (None, "alpha")
    assert station_of("alpha") is None
    assert channel_of("alpha") == "alpha"


def test_a_station_qualified_channel_round_trips():
    key = make_key("focstim", "alpha")
    assert key == "focstim:alpha"
    assert parse_key(key) == ("focstim", "alpha")
    assert station_of(key) == "focstim"
    assert channel_of(key) == "alpha"


def test_a_stations_own_main_stays_qualified():
    # `stations/tcode/<stem>.funscript` is a device-clamped stroke file, not
    # the universal one, so it must not collapse to plain "main".
    assert make_key("tcode", "main") == "tcode:main"
    assert parse_key("tcode:main") == ("tcode", "main")
    assert "main" != make_key("tcode", "main")


def test_folder_layout_mirrors_a_funscriptforge_export():
    # The universal stroke script rides at the top level.
    assert funscript_relpath("main", "combined").as_posix() == "combined.funscript"
    # Station channels go in that device's folder, under FSF's own labels.
    assert funscript_relpath("estim3p:alpha", "combined").as_posix() == (
        "E-Stim/combined.alpha.funscript"
    )
    assert funscript_relpath("focstim:alpha", "combined").as_posix() == (
        "FOC-Stim/combined.alpha.funscript"
    )
    assert funscript_relpath("focstim4p:e1", "combined").as_posix() == (
        "FOC-Stim 4-phase/combined.e1.funscript"
    )
    # A station's own L0 keeps the suffix-less spelling inside its folder.
    assert funscript_relpath("tcode:main", "combined").as_posix() == (
        "MultiFunPlayer/combined.funscript"
    )


def test_three_stations_never_share_an_output_path():
    paths = {
        funscript_relpath(f"{sid}:alpha", "combined").as_posix()
        for sid in ("estim3p", "focstim")
    }
    assert len(paths) == 2


def test_an_unattributed_channel_still_finds_its_device_folder():
    # A loose `<stem>.alpha.funscript` beside a video carries no station, but
    # it is still an e-stim channel — it should not land in a flat heap.
    assert funscript_relpath("alpha", "combined").as_posix() == (
        "E-Stim/combined.alpha.funscript"
    )
    assert funscript_relpath("surge", "combined").as_posix() == (
        "MultiFunPlayer/combined.surge.funscript"
    )
    assert funscript_relpath("e3", "combined").as_posix() == (
        "FOC-Stim 4-phase/combined.e3.funscript"
    )


def test_a_channel_no_station_claims_stays_at_the_top():
    assert funscript_relpath("wibble", "combined").as_posix() == "combined.wibble.funscript"
    assert bundle_relpath("wibble", "combined") == "combined.wibble.funscript"


def test_bundle_layout_is_ffmeta_shaped():
    assert bundle_relpath("main", "combined") == "motion.funscript"
    assert bundle_relpath("estim3p:alpha", "combined") == (
        "stations/estim3p/combined.alpha.funscript"
    )
    assert bundle_relpath("focstim4p:e4", "combined") == (
        "stations/focstim4p/combined.e4.funscript"
    )
    # A station's own L0 has no channel suffix — FunscriptForge's own shape.
    assert bundle_relpath("tcode:main", "combined") == (
        "stations/tcode/combined.funscript"
    )
    # An unattributed channel is placed by its default station, so it imports
    # back into the right device rather than sitting loose at the root.
    assert bundle_relpath("alpha", "combined") == (
        "stations/estim3p/combined.alpha.funscript"
    )


def test_unknown_station_folder_falls_back_the_way_funscriptforge_does():
    assert station_folder("estim3p") == "E-Stim"
    assert station_folder("brand_new") == "Brand New"


# ── Grouped output layout ──────────────────────────────────────────────

def test_grouped_tucks_device_folders_under_estim_and_haptic():
    from forgeassembler_core.channels import GROUPED

    assert funscript_relpath("estim3p:alpha", "lqr1", GROUPED).as_posix() == (
        "estim/E-Stim/lqr1.alpha.funscript"
    )
    assert funscript_relpath("focstim4p:e1", "lqr1", GROUPED).as_posix() == (
        "estim/FOC-Stim 4-phase/lqr1.e1.funscript"
    )
    assert funscript_relpath("tcode:surge", "lqr1", GROUPED).as_posix() == (
        "haptic/MultiFunPlayer/lqr1.surge.funscript"
    )
    assert funscript_relpath("handy:handy", "lqr1", GROUPED).as_posix() == (
        "haptic/Handy/lqr1.handy.funscript"
    )


def test_the_universal_stroke_script_stays_at_the_top_in_both_layouts():
    """It is the file most players want, and burying it is the opposite of
    what grouping is for."""
    from forgeassembler_core.channels import FLAT, GROUPED

    for layout in (FLAT, GROUPED):
        assert funscript_relpath("main", "lqr1", layout).as_posix() == (
            "lqr1.funscript"
        )


def test_a_station_own_stroke_track_is_still_qualified_when_grouped():
    from forgeassembler_core.channels import GROUPED

    assert funscript_relpath("tcode:main", "lqr1", GROUPED).as_posix() == (
        "haptic/MultiFunPlayer/lqr1.funscript"
    )


def test_an_unattributed_channel_stays_at_the_top_when_grouped():
    """Nothing claims it, so no group can. Inventing one would hide it."""
    from forgeassembler_core.channels import GROUPED

    assert funscript_relpath("wibble", "lqr1", GROUPED).as_posix() == (
        "lqr1.wibble.funscript"
    )


def test_an_unknown_station_is_assumed_haptic():
    from forgeassembler_core.channels import GROUPED, station_group

    assert station_group("some_new_toy") == "haptic"
    assert funscript_relpath("some_new_toy:main", "lqr1", GROUPED).as_posix() == (
        "haptic/Some New Toy/lqr1.funscript"
    )


def test_only_the_main_heatmap_moves_to_art():
    """Thirty heatmaps in one folder say nothing about which script each
    belongs to; beside the funscript, the pairing IS the filename."""
    from forgeassembler_core.channels import FLAT, GROUPED, heatmap_relpath

    assert heatmap_relpath("main", "lqr1", FLAT).as_posix() == "lqr1.heatmap.png"
    assert heatmap_relpath("main", "lqr1", GROUPED).as_posix() == (
        "art/lqr1.heatmap.png"
    )
    assert heatmap_relpath("estim3p:alpha", "lqr1", GROUPED).as_posix() == (
        "estim/E-Stim/lqr1.alpha.heatmap.png"
    )
    assert heatmap_relpath("estim3p:alpha", "lqr1", FLAT).as_posix() == (
        "E-Stim/lqr1.alpha.heatmap.png"
    )


def test_audio_goes_to_sound_including_the_estim_wavs():
    """They are files you can play, which is what sound/ means. estim/ holds
    scripts a device reads."""
    from forgeassembler_core.channels import FLAT, GROUPED, audio_relpath

    assert audio_relpath("mp3", "lqr1", FLAT).as_posix() == "lqr1.mp3"
    assert audio_relpath("mp3", "lqr1", GROUPED).as_posix() == "sound/lqr1.mp3"
    assert audio_relpath("prostate.stereostim.wav", "lqr1", GROUPED).as_posix() == (
        "sound/lqr1.prostate.stereostim.wav"
    )


def test_an_unknown_layout_is_refused_rather_than_silently_flat():
    """A typo that fell through to flat would look like the feature never
    landed, not like a bad argument."""
    import pytest as _pytest

    from forgeassembler_core.channels import audio_relpath, heatmap_relpath

    for fn in (funscript_relpath, heatmap_relpath):
        with _pytest.raises(ValueError, match="unknown output layout"):
            fn("main", "lqr1", "Grouped")
    with _pytest.raises(ValueError, match="unknown output layout"):
        audio_relpath("mp3", "lqr1", "nested")


def test_the_bundle_layout_is_untouched_by_grouping():
    """A `.forge` is a portable scene, not a folder someone browses — its
    internal paths are a contract with FunscriptForge and ForgePlayer."""
    from forgeassembler_core.channels import bundle_relpath

    assert bundle_relpath("main", "lqr1") == "motion.funscript"
    assert bundle_relpath("estim3p:alpha", "lqr1") == (
        "stations/estim3p/lqr1.alpha.funscript"
    )
