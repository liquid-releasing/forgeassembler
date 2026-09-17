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
    "DEFAULT_STATION",
    "MAIN",
    "STATION_FOLDER",
    "STATION_SEP",
    "bundle_relpath",
    "channel_of",
    "funscript_relpath",
    "make_key",
    "parse_key",
    "station_folder",
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


def funscript_relpath(key: str, stem: str) -> Path:
    """Where `key` is written inside a forge's output FOLDER.

    Main rides at the top as `<stem>.funscript` — the universal stroke script
    most players want, exactly as FunscriptForge places it. Everything else
    goes in its device folder.
    """
    if key == MAIN:
        return Path(f"{stem}.funscript")
    station, channel = with_station(key)
    name = f"{stem}.funscript" if channel == MAIN else f"{stem}.{channel}.funscript"
    return Path(station_folder(station)) / name if station else Path(name)


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
