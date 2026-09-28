# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Read back what a forge WROTE, for the Viewer tab.

The Build tab's preview answers "what will this be"; this answers "what did I
actually get". They are different questions and the second one is the only one
that can catch a title card that rendered invisible, a channel that came out
flat, or a scene that starts three seconds late. Until now the answer required
leaving the app.

Two sources, in this order:

  1. the ``.forge`` bundle, which carries the channels AND the context lanes
     (``chapters.json``, ``beats.json``, ``audio.json``) in one file;
  2. the loose output folder — ``<stem>.funscript`` at the top and one folder
     per station beside it, which is what `channels.funscript_relpath` writes.

The bundle wins when both exist because it is the richer artifact, and because
it is the one that travels: see the standing rule that the ``.forge`` FILE is
the source of truth, never a ``.<stem>.forge/`` working folder.

This module is pure file IO. It never re-derives anything from the project —
if the forge wrote it wrong, the Viewer shows it wrong, which is the entire
point of a review surface.
"""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Optional

from .channels import MAIN, STATION_FOLDER, station_folder, with_station
from .project import RESOLUTION_FILENAME_LABEL

# Ordered, unlike `_MEDIA_EXTS` below: this drives which extension wins when a
# folder holds more than one, so it must not be a set.
_MEDIA_PREFERRED = (".mp4", ".mkv", ".mov", ".m4v")

# A render tag as `video_filename` writes it: a size label welded to the frame
# rate, e.g. `4k25`, `uw1440p60`. Longest labels first so `1080p` cannot be
# shadowed by a shorter alternative that happens to prefix it.
_RENDER_TAG = re.compile(
    "^(?:"
    + "|".join(sorted(
        (re.escape(v) for v in set(RESOLUTION_FILENAME_LABEL.values())),
        key=len, reverse=True,
    ))
    + r")\d+$",
)

# `Best Of.4k30.tmp.10344.mp4` -- a forge writing right now. It is a partial
# file and it is about to be renamed away, so nothing may read it: not as a
# render to play, and not as evidence of what this folder is called.
_TEMP_RENDER = re.compile(r"\.tmp\.\d+$")


def _find_media(folder: Path, stem: str) -> Optional[Path]:
    """The video to run in the monitor, or None.

    A forge used to write `<stem>.mp4`. It now writes `<stem>.<tag>.mp4`
    -- `Best Of.4k25.mp4` -- so that a 4K copy to keep and a 1080p copy to
    send can sit in one folder without overwriting each other. Looking only
    for the untagged name left the monitor with nothing to play.

    Untagged wins when present: that is what an older forge wrote, and what
    a file the user renamed by hand looks like. Otherwise the newest tagged
    rendition -- several coexist by design, and the Viewer exists to check
    the render you just made.

    Matching the tag SHAPE rather than globbing `<stem>.*` is what keeps
    `<stem>.tmp.10344.mp4`, the half-written temp of a forge still running,
    from being offered up as the finished article.
    """
    for ext in _MEDIA_PREFERRED:
        exact = folder / f"{stem}{ext}"
        if exact.is_file():
            return exact

    candidates: list[Path] = []
    try:
        entries = list(folder.iterdir())
    except OSError:
        return None
    for p in entries:
        # Not `folder.glob(stem + ".*")`: a stem is a user-chosen filename,
        # and one containing `[` or `?` would be read as a glob pattern and
        # silently match nothing.
        if p.suffix.lower() not in _MEDIA_EXTS or not p.is_file():
            continue
        if not p.name.startswith(stem + "."):
            continue
        middle = p.name[len(stem) + 1: len(p.name) - len(p.suffix)]
        if _RENDER_TAG.match(middle):
            candidates.append(p)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)

__all__ = [
    "load_output",
    "load_single_channel",
    "resolve_source",
]

# The universal stroke track has no station folder, so it needs a name of its
# own in the device picker. Not a station id — it is the track every device
# derives from.
STROKE_DEVICE = "Stroke"

# Folder names that are output, not devices. `thumbnails/` is the forge's own;
# `audio/` holds the rendered estim WAV/MP3s, which are not funscripts anyway.
_NON_DEVICE_DIRS = {"thumbnails", "audio", "preview", "__pycache__"}

_MEDIA_EXTS = {".mp4", ".mkv", ".mov", ".m4v", ".webm", ".avi", ".wmv"}

# Devices in the order a person thinks about them: the stroke track first,
# then the stations in `STATION_FOLDER`'s order, then anything unrecognised.
_DEVICE_ORDER = [STROKE_DEVICE] + list(STATION_FOLDER.values())


def _device_sort_key(name: str) -> tuple:
    try:
        return (0, _DEVICE_ORDER.index(name), name)
    except ValueError:
        return (1, 0, name)


def _channel_sort_key(name: str) -> tuple:
    # `main` first — a station's own stroke track is the one to read first.
    return (0, "") if name == MAIN else (1, name)


# ── decimation ───────────────────────────────────────────────────────
def _decimate(actions: list[dict], max_points: int) -> list[dict]:
    """Peak-preserving decimation: keep min+max position per time bin.

    A naive stride would drop whichever samples it landed between, and a
    stroke envelope thinned that way loses exactly the peaks the Viewer exists
    to show. Binning and emitting each bin's lowest AND highest point keeps
    the envelope while cutting the transport cost.
    """
    n = len(actions)
    if n <= max_points or max_points < 4:
        return [{"at": int(a["at"]), "pos": int(a["pos"])} for a in actions]
    bins = max_points // 2
    out: list[dict] = []
    for i in range(bins):
        lo = (i * n) // bins
        hi = max(lo + 1, ((i + 1) * n) // bins)
        seg = actions[lo:hi]
        amin = min(seg, key=lambda a: a["pos"])
        amax = max(seg, key=lambda a: a["pos"])
        first, second = (amin, amax) if amin["at"] <= amax["at"] else (amax, amin)
        out.append({"at": int(first["at"]), "pos": int(first["pos"])})
        if second is not first:
            out.append({"at": int(second["at"]), "pos": int(second["pos"])})
    return out


def _stride_decimate(actions: list[dict], cap: int) -> list[dict]:
    """Time-uniform thinning for the monitor's windowed view.

    The opposite trade from `_decimate`: the monitor zooms to a few seconds,
    where a min/max envelope's low+high PAIRS per bin read as a zigzag rather
    than as strokes. Keeping every k-th real sample keeps the curve monotonic
    in time, so the shape is the true one.
    """
    n = len(actions)
    if cap <= 0 or n <= cap:
        return [{"at": int(a["at"]), "pos": int(a["pos"])} for a in actions]
    k = (n + cap - 1) // cap
    out = [{"at": int(actions[i]["at"]), "pos": int(actions[i]["pos"])}
           for i in range(0, n, k)]
    last = actions[-1]
    if out[-1]["at"] != int(last["at"]):
        out.append({"at": int(last["at"]), "pos": int(last["pos"])})
    return out


def _decimate_peaks(peaks: list, target: int) -> list:
    n = len(peaks)
    if n <= target or target < 1:
        return list(peaks)
    k = (n + target - 1) // target
    return [max(peaks[i:i + k]) for i in range(0, n, k)]


# ── locating the output ──────────────────────────────────────────────
def _channel_from_filename(filename: str, stem: str) -> str:
    """``<stem>.<channel>.funscript`` → ``<channel>``.

    A station's own stroke track is written suffix-less (``<stem>.funscript``
    inside the station's folder), so that spelling means `main`. Splitting on
    the LAST dots rather than the first is what keeps a dotted stem — `s1.v2`
    — from being read as a channel called `v2`.
    """
    name = filename[:-len(".funscript")] if filename.endswith(".funscript") else filename
    if name == stem:
        return MAIN
    if name.startswith(stem + "."):
        return name[len(stem) + 1:]
    # Unrelated stem (a hand-dropped file): take everything after the first dot,
    # or the whole name when there is none.
    return name.split(".", 1)[1] if "." in name else name


def _strip_render_tag(stem: str) -> str:
    """`It's Just AI Sex.4k30` -> `It's Just AI Sex`; anything else unchanged."""
    head, _, tail = stem.rpartition(".")
    return head if head and _RENDER_TAG.match(tail) else stem


def _stem_for_folder(folder: Path) -> Optional[str]:
    """Which stem a forged output folder belongs to.

    In order of authority: the `.forge` bundle, then the video, then a
    top-level funscript, and only then the project file. Guessing from the
    first file alphabetically would pick a stray.

    The project file comes LAST, though it used to come first. Its name is
    the PROJECT's -- `its-just-ai-sex.forgeproject` -- while every output is
    named from `output.basename`, `It's Just AI Sex`. Those are separate
    fields and a user who renames one does not rename the other, so trusting
    the project file made the Viewer hunt for files under a name nothing on
    disk used: no video, no chapters, no bundle. It stays in the list only
    as a last resort for a folder whose outputs are gone.

    The video's own stem carries the render tag (`.4k30`), which is likewise
    not the stem the funscripts and sidecars use -- hence the strip.
    """
    bundles = sorted(folder.glob("*.forge"),
                     key=lambda p: p.stat().st_mtime, reverse=True)
    if bundles:
        return bundles[0].stem

    vids = sorted((p for p in folder.iterdir()
                   if p.is_file() and p.suffix.lower() in _MEDIA_EXTS
                   and not _TEMP_RENDER.search(p.stem)),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    if vids:
        return _strip_render_tag(vids[0].stem)

    funs = sorted(folder.glob("*.funscript"))
    if funs:
        return funs[0].name[:-len(".funscript")]

    for pattern in ("*.forgeproject", "*.forgeproject.json"):
        hits = sorted(folder.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        if hits:
            name = hits[0].name
            for suffix in (".forgeproject.json", ".forgeproject"):
                if name.endswith(suffix):
                    return name[:-len(suffix)]
    return None


def resolve_source(path: str) -> Optional[tuple[str, Path, str]]:
    """``(kind, path, stem)`` for whatever the user opened, or None.

    Accepts the forged video, the ``.forge`` bundle, the ``.forgeproject``, a
    funscript, or the output folder itself — because all five are things a
    person might reasonably double-click, and making them guess which one the
    Viewer wants is a worse experience than trying each.
    """
    p = Path(path)
    if not p.exists():
        return None

    if p.is_dir():
        stem = _stem_for_folder(p)
        if not stem:
            return None
        bundle = p / f"{stem}.forge"
        if bundle.is_file():
            return ("forge", bundle, stem)
        return ("folder", p, stem)

    if p.suffix.lower() == ".forge":
        return ("forge", p, p.stem)

    name = p.name
    stem = p.stem
    for suffix in (".forgeproject.json", ".forgeproject"):
        if name.endswith(suffix):
            stem = name[:-len(suffix)]
            break

    folder = p.parent
    bundle = folder / f"{stem}.forge"
    if bundle.is_file():
        return ("forge", bundle, stem)
    return ("folder", folder, stem)


# ── reading the channels ─────────────────────────────────────────────
def _actions_of(raw: bytes | str) -> list[dict]:
    try:
        data = json.loads(raw)
    except Exception:
        return []
    acts = data.get("actions") if isinstance(data, dict) else None
    if not isinstance(acts, list):
        return []
    out = []
    for a in acts:
        try:
            out.append({"at": int(a["at"]), "pos": int(a["pos"])})
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _from_folder(folder: Path, stem: str, max_points: int) -> dict:
    """Devices from a loose output folder.

    Handles BOTH shapes a forge has written, because both are on real disks:

      foldered  <stem>.funscript  +  E-Stim/<stem>.alpha.funscript
      flat      <stem>.funscript  +  <stem>.alpha.funscript

    The flat one is what forges wrote before station folders landed, and it is
    still what a hand-assembled set beside a video looks like. A flat channel
    is attributed the same way the forge attributes one — `with_station`, then
    `station_folder` — so the SAME file lands under the same device name
    whichever layout it arrived in. Reading only the folders found 1 channel
    of 16 in a real September output.
    """
    by_device: dict[str, list[dict]] = {}
    duration_ms = 0

    def read(f: Path, name: Optional[str] = None) -> Optional[dict]:
        nonlocal duration_ms
        try:
            acts = _actions_of(f.read_bytes())
        except OSError:
            return None
        if len(acts) < 2:
            return None
        duration_ms = max(duration_ms, acts[-1]["at"])
        return {
            "name": name or _channel_from_filename(f.name, stem),
            "actions": _decimate(acts, max_points),
            "rawCount": len(acts),
        }

    for f in sorted(folder.glob("*.funscript")):
        channel = _channel_from_filename(f.name, stem)
        if f.name == f"{stem}.funscript":
            # At the top level THIS file is the universal stroke track.
            ch = read(f, MAIN)
            if ch:
                by_device.setdefault(STROKE_DEVICE, []).append(ch)
            continue
        ch = read(f, channel)
        if not ch:
            continue
        station, _ = with_station(channel)
        # No station claims it: it belongs beside the stroke track, not under
        # a device invented for it.
        device = station_folder(station) if station else STROKE_DEVICE
        by_device.setdefault(device, []).append(ch)

    for d in sorted(folder.iterdir(), key=lambda x: x.name):
        if not d.is_dir() or d.name.lower() in _NON_DEVICE_DIRS:
            continue
        for f in sorted(d.glob("*.funscript")):
            ch = read(f)
            if ch:
                by_device.setdefault(d.name, []).append(ch)

    devices = []
    for name, chans in by_device.items():
        # A channel can arrive twice only if the same output holds both
        # layouts. The foldered copy is the newer convention, and it is read
        # second, so keeping the first-seen spelling would prefer the stale one.
        seen: dict[str, dict] = {}
        for c in chans:
            seen[c["name"]] = c
        merged = sorted(seen.values(), key=lambda c: _channel_sort_key(c["name"]))
        devices.append({"name": name, "channels": merged})
    devices.sort(key=lambda dev: _device_sort_key(dev["name"]))

    return {"available": bool(devices), "devices": devices, "durationMs": duration_ms}


def _from_bundle(bundle: Path, stem: str, max_points: int) -> dict:
    """Devices from a ``.forge`` zip: ``motion.funscript`` plus
    ``stations/<id>/<stem>.<channel>.funscript``."""
    try:
        z = zipfile.ZipFile(bundle)
    except Exception:
        return {"available": False, "error": "unreadable .forge", "devices": []}

    duration_ms = 0
    by_station: dict[str, list[dict]] = {}
    stroke: list[dict] = []

    def read(entry: str, channel: str) -> Optional[dict]:
        nonlocal duration_ms
        try:
            acts = _actions_of(z.read(entry))
        except Exception:
            return None
        if len(acts) < 2:
            return None
        duration_ms = max(duration_ms, acts[-1]["at"])
        return {"name": channel, "actions": _decimate(acts, max_points),
                "rawCount": len(acts)}

    with z:
        for entry in z.namelist():
            if not entry.endswith(".funscript"):
                continue
            parts = entry.split("/")
            if entry == "motion.funscript":
                ch = read(entry, MAIN)
                if ch:
                    stroke.append(ch)
            elif len(parts) == 3 and parts[0] == "stations":
                ch = read(entry, _channel_from_filename(parts[2], stem))
                if ch:
                    # The station id, mapped to the folder name a person
                    # recognises — `estim3p` means nothing, `E-Stim` does.
                    label = STATION_FOLDER.get(parts[1], parts[1])
                    by_station.setdefault(label, []).append(ch)

    devices: list[dict] = []
    if stroke:
        devices.append({"name": STROKE_DEVICE, "channels": stroke})
    for label, chans in by_station.items():
        chans.sort(key=lambda c: _channel_sort_key(c["name"]))
        devices.append({"name": label, "channels": chans})
    devices.sort(key=lambda d: _device_sort_key(d["name"]))

    return {"available": bool(devices), "devices": devices, "durationMs": duration_ms}


# ── the context lanes ────────────────────────────────────────────────
def _bundle_json(bundle: Path, endswith: str) -> Optional[dict]:
    try:
        with zipfile.ZipFile(bundle) as z:
            hit = next((n for n in z.namelist() if n.endswith(endswith)), None)
            if hit:
                return json.loads(z.read(hit).decode("utf-8"))
    except Exception:
        return None
    return None


def _shape_chapters(raw: Optional[dict]) -> list[dict]:
    """``chapters.json`` (audio-structure v3.0) → ``{start, end, name, tone}``."""
    if not raw:
        return []
    chs = raw.get("chapters") if isinstance(raw, dict) else raw
    out = []
    for i, c in enumerate(chs or []):
        start, end = c.get("at_ms"), c.get("end_ms")
        if start is None or end is None:
            continue
        out.append({
            "start": int(start), "end": int(end),
            "name": c.get("name") or f"Chapter {i + 1}",
            "tone": c.get("tone", ""), "color": c.get("color", ""),
        })
    return out


def _shape_audio(raw: Optional[dict], target: int) -> Optional[dict]:
    if not raw:
        return None
    peaks = raw.get("peaks")
    if not peaks:
        return None
    dur = raw.get("duration_ms") or raw.get("durationMs") or 0
    dec = _decimate_peaks(peaks, target)
    # Derive the hop from the decimated length rather than carrying the
    # original: after decimation the stored `hop_ms` describes samples that no
    # longer exist, and the lane would draw the waveform at the wrong scale.
    hop = (dur / len(dec)) if (dur and dec) else (raw.get("hop_ms") or raw.get("hopMs") or 10)
    return {"peaks": dec, "hopMs": hop, "durationMs": dur}


def _shape_beats(raw: Optional[dict]) -> Optional[dict]:
    if not raw:
        return None
    beats = raw.get("beats_ms") or raw.get("beatsMs") or []
    if not beats:
        return None
    return {
        "bpm": raw.get("bpm"),
        "beatsMs": [int(b) for b in beats],
        "downbeatsMs": [int(b) for b in (raw.get("downbeats_ms")
                                         or raw.get("downbeatsMs") or [])],
    }


def _sidecar(folder: Path, stem: str, name: str) -> Optional[dict]:
    p = folder / f"{stem}.{name}.json"
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


# ── the public loaders ───────────────────────────────────────────────
def load_output(path: str, *, max_points: int = 2000, audio_points: int = 16000) -> dict:
    """Everything the Viewer needs about one forged output.

    Returns ``{available, devices, durationMs, chapters, audio, beats,
    source, sourceName, sourcePath, mediaPath}``.
    """
    resolved = resolve_source(path)
    if resolved is None:
        return {"available": False, "devices": [],
                "error": "nothing to review at that path"}
    kind, src, stem = resolved

    res = (_from_bundle(src, stem, max_points) if kind == "forge"
           else _from_folder(src, stem, max_points))

    res["source"] = kind
    res["sourcePath"] = str(src)
    # A bundle IS one file, so its filename names the output. A folder is not:
    # its name is wherever the user happened to save ("forgeassembler"), which
    # tells you nothing about which compilation you are looking at. The stem
    # does.
    res["sourceName"] = src.name if kind == "forge" else stem

    if not res.get("available"):
        res.setdefault("error", "no funscripts in the forged output")
        return res

    folder = src.parent if kind == "forge" else src

    # Context lanes. The bundle carries all three; a loose folder may have the
    # sidecars beside it. Missing ones are None, and the lane simply is not drawn.
    if kind == "forge":
        res["chapters"] = _shape_chapters(_bundle_json(src, "chapters.json"))
        res["audio"] = _shape_audio(_bundle_json(src, "audio.json"), audio_points)
        res["beats"] = _shape_beats(_bundle_json(src, "beats.json"))
    else:
        res["chapters"] = _shape_chapters(_sidecar(folder, stem, "chapters"))
        res["audio"] = _shape_audio(_sidecar(folder, stem, "audio"), audio_points)
        res["beats"] = _shape_beats(_sidecar(folder, stem, "beats"))

    # The video to run in the monitor. The bundle does not carry it by default
    # (a compilation is measured in gigabytes), so look for it on disk.
    media = _find_media(folder, stem)
    res["mediaPath"] = str(media) if media else None
    return res


def load_single_channel(path: str, device: str, channel: str, *,
                        cap: int = 40000) -> dict:
    """One channel at full resolution, for the monitor's windowed view.

    Returns ``{available, name, actions, rawCount}``. The monitor shows a few
    seconds at a time, where the timeline's min/max envelope is the wrong
    shape — see `_stride_decimate`.
    """
    resolved = resolve_source(path)
    if resolved is None:
        return {"available": False, "name": channel, "actions": [], "rawCount": 0}
    kind, src, stem = resolved

    acts: list[dict] = []
    if kind == "forge":
        try:
            with zipfile.ZipFile(src) as z:
                names = z.namelist()
                if device == STROKE_DEVICE:
                    hit = "motion.funscript" if "motion.funscript" in names else None
                else:
                    ids = [k for k, v in STATION_FOLDER.items() if v == device] or [device]
                    hit = next(
                        (n for n in names
                         if n.startswith("stations/") and n.endswith(".funscript")
                         and n.split("/")[1] in ids
                         and _channel_from_filename(n.split("/")[-1], stem) == channel),
                        None)
                if hit:
                    acts = _actions_of(z.read(hit))
        except Exception:
            acts = []
    else:
        name = f"{stem}.funscript" if channel == MAIN else f"{stem}.{channel}.funscript"
        # Both layouts again, and in the same order the timeline reads them,
        # or the monitor would come back blank for every flat output while
        # the lane beside it drew the channel perfectly well.
        if device == STROKE_DEVICE:
            candidates = [src / name]
        else:
            candidates = [src / device / name]
            # The flat fallback, but NEVER for a station's own `main`: flat,
            # `<stem>.funscript` is the UNIVERSAL stroke track, and serving it
            # as `E-Stim/main` would show one channel's data under another
            # channel's name — the one thing the monitor must never do.
            if channel != MAIN:
                candidates.append(src / name)
        for f in candidates:
            if f.is_file():
                acts = _actions_of(f.read_bytes())
                if len(acts) >= 2:
                    break

    if len(acts) < 2:
        return {"available": False, "name": channel, "actions": [], "rawCount": 0}
    return {"available": True, "name": channel,
            "actions": _stride_decimate(acts, cap), "rawCount": len(acts)}
