# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Station-qualified channel keys — one vocabulary for the whole engine.

A channel used to be identified by its name alone: `alpha`, `surge`, `handy`.
That worked while a FunscriptForge scene shipped one file per channel. It
stopped being true when FOC-Stim landed: `estim3p`, `focstim` and `focstim4p`
all write `alpha`, `beta`, `volume`, `frequency`, `pulse_frequency`,
`pulse_rise_time` and the prostate variants — the SAME names, clamped
differently for each device. A real bundle now carries 39 funscripts across 9
stations, and keying by name alone collapsed them to 24 and silently dropped
15 files, the entire FOC-Stim station among them.

So a channel key is `"<station>:<channel>"` when a station owns the file, and
a bare `"<channel>"` when nothing does (a loose funscript sitting beside a
video). `"main"` is the universal stroke track — the bundle's
`motion.funscript`, FunscriptForge's L0.

The separator is `:` on purpose: it is illegal in a Windows filename, so a key
that leaks into a path fails loudly instead of quietly creating something odd.
Build and read keys only through `make_key` / `parse_key`.

Both output layouts mirror FunscriptForge, which is the only authority on what
these files are called:

  bundle      motion.funscript
              stations/estim3p/<stem>.alpha.funscript
              stations/tcode/<stem>.funscript          (a station's own L0)

  folder      <stem>.funscript                         (universal stroke)
              E-Stim/<stem>.alpha.funscript
              FOC-Stim/<stem>.alpha.funscript
              MultiFunPlayer/<stem>.surge.funscript

The folder labels are FunscriptForge's `_STATION_FOLDER`, so a forge writes
the folder names its users already know from an FSF export.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

__all__ = [
    "ART_FOLDER",
    "DEFAULT_GROUP",
    "DEFAULT_STATION",
    "FLAT",
    "GROUPED",
    "LAYOUTS",
    "MAIN",
    "SOUND_FOLDER",
    "STATION_FOLDER",
    "STATION_GROUP",
    "STATION_SEP",
    "audio_relpath",
    "bundle_relpath",
    "channel_of",
    "funscript_relpath",
    "heatmap_relpath",
    "make_key",
    "parse_key",
    "station_folder",
    "station_group",
    "station_of",
    "with_station",
]

STATION_SEP = ":"
MAIN = "main"

# FunscriptForge's `_STATION_FOLDER` (cli.py), verbatim — the per-device folder
# names an FSF loose export writes. Mirrored so a ForgeAssembler output folder
# and an FSF output folder look the same to the person opening them.
STATION_FOLDER: dict[str, str] = {
    "estim3p": "E-Stim",
    "focstim": "FOC-Stim",
    "focstim4p": "FOC-Stim 4-phase",
    "handy": "Handy",
    "tcode": "MultiFunPlayer",
    "osr2": "OSR2",
    "sr6": "SR6",
    "lovense": "Lovense",
    "vacuglide": "Vacuglide",
    "ossm": "OSSM",
    "shaker": "Bass Shaker",
}

# Which station owns a channel when nothing says. Used for funscripts that
# arrive with no station attribution — a loose `<stem>.alpha.funscript` beside
# a video — so they still land in the right device folder instead of a flat
# heap. Taken from what the stations actually write (measured against a real
# FSF bundle), NOT invented.
#
# The shared e-stim parameter channels (volume, frequency, pulse_*) map to
# estim3p: it is the station every e-stim-capable project has, and an
# unattributed file is far likelier to have come from there than from an
# experimental one.
DEFAULT_STATION: dict[str, str] = {
    # estim3p — three-phase e-stim and its prostate set
    "alpha": "estim3p",
    "beta": "estim3p",
    "alpha-prostate": "estim3p",
    "beta-prostate": "estim3p",
    "volume": "estim3p",
    "volume-prostate": "estim3p",
    "frequency": "estim3p",
    "pulse_frequency": "estim3p",
    "pulse_rise_time": "estim3p",
    "pulse_width": "estim3p",
    # focstim4p — per-electrode powers, which only it writes
    "e1": "focstim4p",
    "e2": "focstim4p",
    "e3": "focstim4p",
    "e4": "focstim4p",
    # tcode — the multi-axis set
    "pitch": "tcode",
    "roll": "tcode",
    "surge": "tcode",
    "sway": "tcode",
    "twist": "tcode",
    # stations whose channel is named after the device
    "handy": "handy",
    "ossm": "ossm",
    "lovense": "lovense",
    "vacuglide": "vacuglide",
    "shaker": "shaker",
}


# ── Output folder layouts ──────────────────────────────────────────────
#
# "flat" is what every forge before this wrote: station folders sitting in the
# output folder beside the video, the audio and the heatmap. It is kept
# because it is what existing outputs look like, and re-forging a project
# should not quietly rearrange a folder someone already publishes from.
#
# "grouped" answers the thing that actually goes wrong with "flat": eleven
# station folders and five audio files bury the three artifacts anyone
# actually opens. Grouped leaves the top level as the forge file, the videos,
# the universal funscript and four folders.
#
#   <stem>.forge  <stem>.4k30.mp4  <stem>.funscript
#   art/     — the main heatmap, title cards, anything else rendered
#   sound/   — every audio file, the e-stim WAVs included
#   estim/   — E-Stim, FOC-Stim, FOC-Stim 4-phase
#   haptic/  — Handy, OSR2, SR6, MultiFunPlayer, Lovense, …
#
# A per-channel heatmap stays BESIDE its funscript in both layouts. Thirty of
# them in one art/ folder tells you nothing about which script each belongs
# to; next to it, the pairing is the filename.
FLAT = "flat"
GROUPED = "grouped"
LAYOUTS: tuple[str, ...] = (FLAT, GROUPED)

SOUND_FOLDER = "sound"
ART_FOLDER = "art"

# Which top-level group a station sits under when grouped.
STATION_GROUP: dict[str, str] = {
    "estim3p": "estim",
    "focstim": "estim",
    "focstim4p": "estim",
    "handy": "haptic",
    "tcode": "haptic",
    "osr2": "haptic",
    "sr6": "haptic",
    "lovense": "haptic",
    "vacuglide": "haptic",
    "ossm": "haptic",
    "shaker": "haptic",
}

# An unknown station drives something -- that is what a station IS. Guessing
# "haptic" puts a newly-supported device beside its peers instead of alone at
# the top level, and being wrong costs one folder.
DEFAULT_GROUP = "haptic"


def station_group(station: str) -> str:
    """The top-level group folder `station` belongs to when grouped."""
    return STATION_GROUP.get(station, DEFAULT_GROUP)


def _check_layout(layout: str) -> str:
    """Normalise a layout name, refusing one we do not write.

    Loudly: a typo here would silently produce the flat layout, and the
    symptom -- files in the wrong place -- looks like the feature never
    landed rather than like a bad argument.
    """
    if layout not in LAYOUTS:
        raise ValueError(
            f"unknown output layout {layout!r}; expected one of {LAYOUTS}",
        )
    return layout


def make_key(station: Optional[str], channel: str) -> str:
    """Build a channel key. With no station the channel stands alone.

    A station's own main track stays qualified (`tcode:main`) — it is a
    device-clamped stroke file, not the universal one.
    """
    if not station:
        return channel
    return f"{station}{STATION_SEP}{channel}"


def parse_key(key: str) -> tuple[Optional[str], str]:
    """Split a channel key into `(station, channel)`.

    A bare key has no station: `parse_key("alpha") == (None, "alpha")`.
    """
    if STATION_SEP in key:
        station, _, channel = key.partition(STATION_SEP)
        if station and channel:
            return station, channel
    return None, key


def station_of(key: str) -> Optional[str]:
    """The station that owns `key`, or None if it is unattributed."""
    return parse_key(key)[0]


def channel_of(key: str) -> str:
    """The channel name inside `key`, with any station stripped."""
    return parse_key(key)[1]


def with_station(key: str) -> tuple[str, str]:
    """`(station, channel)` for `key`, falling back to `DEFAULT_STATION`.

    The station may still be `""` for a channel nothing claims — callers
    place those at the top level rather than inventing a device for them.
    """
    station, channel = parse_key(key)
    return station or DEFAULT_STATION.get(channel, ""), channel


def station_folder(station: str) -> str:
    """The output folder name for `station`.

    Unknown ids title-case, matching FunscriptForge's own fallback, so a
    station added there shows up sensibly here before we learn its name.
    """
    return STATION_FOLDER.get(station) or station.replace("_", " ").title()


def funscript_relpath(key: str, stem: str, layout: str = FLAT) -> Path:
    """Where `key` is written inside a forge's output FOLDER.

    Main rides at the top as `<stem>.funscript` — the universal stroke script
    most players want, exactly as FunscriptForge places it, and it stays there
    in BOTH layouts. Everything else goes in its device folder, which the
    grouped layout tucks under `estim/` or `haptic/`.
    """
    _check_layout(layout)
    if key == MAIN:
        return Path(f"{stem}.funscript")
    station, channel = with_station(key)
    name = f"{stem}.funscript" if channel == MAIN else f"{stem}.{channel}.funscript"
    if not station:
        return Path(name)
    folder = Path(station_folder(station))
    if layout == GROUPED:
        folder = Path(station_group(station)) / folder
    return folder / name


def heatmap_relpath(key: str, stem: str, layout: str = FLAT) -> Path:
    """Where `key`'s companion heatmap PNG goes.

    Beside its funscript, so the pairing is the filename — except the main
    one, which grouped moves to `art/`. That single PNG is the only heatmap
    that sits at the top level, and the top level is what grouping is for.
    """
    _check_layout(layout)
    if key == MAIN and layout == GROUPED:
        return Path(ART_FOLDER) / f"{stem}.heatmap.png"
    script = funscript_relpath(key, stem, layout)
    return script.with_name(f"{script.stem}.heatmap.png")


def audio_relpath(channel_key: str, stem: str, layout: str = FLAT) -> Path:
    """Where a concatenated audio/e-stim channel is written.

    `channel_key` already carries the extension — "mp3", "prostate.mp3",
    "stereostim.wav" — so the name is just `<stem>.<channel_key>`.

    The e-stim WAVs live here with the rest of the audio rather than under
    `estim/` with the e-stim funscripts. They are the same kind of thing as
    the MP3s: a file you can play. `estim/` holds scripts a device reads.
    """
    _check_layout(layout)
    name = f"{stem}.{channel_key}"
    return Path(SOUND_FOLDER) / name if layout == GROUPED else Path(name)


def bundle_relpath(key: str, stem: str) -> str:
    """Where `key` is written inside a `.forge` bundle (posix, ffmeta/v1).

    Main is `motion.funscript`. A station's own L0 keeps FunscriptForge's
    suffix-less spelling (`stations/tcode/<stem>.funscript`). A channel no
    station claims sits at the bundle root, where an importer's suffix split
    still reads it correctly.
    """
    if key == MAIN:
        return "motion.funscript"
    station, channel = with_station(key)
    name = f"{stem}.funscript" if channel == MAIN else f"{stem}.{channel}.funscript"
    return f"stations/{station}/{name}" if station else name
