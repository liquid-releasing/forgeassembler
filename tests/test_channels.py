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
