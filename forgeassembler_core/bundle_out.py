# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Write the joined compilation as a `.forge` bundle.

ForgeAssembler's job is to take finished FunscriptForge scenes, clip and fade
them as the author specified, and join them. Until now the result was a folder
of loose files — an MP4 and a pile of funscripts — which is playable but is
not a SCENE. FunscriptForge could not reopen it and ForgePlayer could not see
it as one thing, so the compilation fell out of the forge family the moment it
was forged.

This writes the same `ffmeta/v1` bundle FunscriptForge writes, because
FunscriptForge is the format's author and a second dialect would be a bug.
Verified against a real export (`cli.py export --mode forge`), which for a
chapters-rich project ships 39 funscripts across 9 stations, three analysis
sidecars, three audio renders, and a `media` block with no media in it:

    manifest.ffmeta
    motion.funscript                      # the universal stroke track
    stations/<id>/<stem>.<channel>.funscript
    audio/stim.mp3  stim-prostate.mp3  beat.mp3
    chapters.json  beats.json  audio.json
    thumbnails/hero.png  chapter_NN.png

Two things are ForgeAssembler's own and deliberately so:

  * `created_with` says ForgeAssembler, so a consumer can tell a compilation
    from an authored scene;
  * `compilation` lists which scenes went in, with their lineage — the one
    fact only the assembler knows, and the one a person asking "what is this
    two-hour file made of?" most wants.

MEDIA IS NOT BUNDLED by default, matching FunscriptForge's lean export: a
joined compilation is measured in gigabytes. The manifest carries the same
relink key FSF stamps (name, size, hash of the first MiB), which is how the
importer on either side finds the video again.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import time
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Optional

from .channels import bundle_relpath, station_of, with_station

if TYPE_CHECKING:
    from .layout import Layout
    from .project import Project

__all__ = [
    "AUDIO_ROLE_FOR_CHANNEL",
    "compilation_chapters",
    "join_audio_peaks",
    "join_beats",
    "media_provenance",
    "write_forge_bundle",
]

MANIFEST_NAME = "manifest.ffmeta"
MOTION_NAME = "motion.funscript"

# Provenance hashes only the head of the file — enough to tell two videos
# apart, cheap on a multi-gigabyte render. Same size FunscriptForge uses, so
# the keys it stamps and the keys we stamp are comparable.
_PROVENANCE_HEAD_BYTES = 1024 * 1024
_PROVENANCE_VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"}

# The engine names a joined audio channel after the file suffix it came from
# ("mp3", "prostate.mp3", "beat.mp3"). A bundle names it by ROLE and puts it
# under `audio/`. This is the inverse of `forge_bundle._AUDIO_ROLE_SUFFIX`,
# so a bundle's audio survives a round trip through a compilation.
AUDIO_ROLE_FOR_CHANNEL: dict[str, tuple[str, str]] = {
    # channel key            -> (role, bundle basename)
    "mp3": ("estim", "stim"),
    "wav": ("estim", "stim"),
    "prostate.mp3": ("estim-prostate", "stim-prostate"),
    "prostate.wav": ("estim-prostate", "stim-prostate"),
    "stereostim.wav": ("estim", "stim"),
    "prostate.stereostim.wav": ("estim-prostate", "stim-prostate"),
    "beat.mp3": ("beat", "beat"),
    "beat.wav": ("beat", "beat"),
}

# Target grid for the joined waveform. FunscriptForge writes 10 ms peaks; a
# compilation of scenes that agree on that needs no resampling at all.
_PEAK_HOP_MS = 10


def media_provenance(media_path: Path) -> dict:
    """A relink key for `media_path`, in FunscriptForge's exact shape.

    Name + size + a hash of the first MiB. The consumer finds the file by
    name and confirms it with the size and hash, which is what makes a lean
    bundle safe to hand to someone who already has the video.
    """
    st = media_path.stat()
    h = hashlib.sha256()
    with open(media_path, "rb") as f:
        h.update(f.read(_PROVENANCE_HEAD_BYTES))
    return {
        "filename": media_path.name,
        "size": st.st_size,
        "head_sha256": h.hexdigest(),
        "kind": "video" if media_path.suffix.lower() in _PROVENANCE_VIDEO_EXTS else "audio",
    }


# ── the compilation's own chapters ───────────────────────────────────
def compilation_chapters(project: "Project", layout: "Layout") -> dict:
    """A `chapters.json` (schema `audio-structure` v3.0) for the compilation.

    One chapter per SECTION, which is what a section IS — the same list the
    MP4's markers and every channel funscript already carry, so a player and
    an editor cannot disagree about where a scene starts.

    The input scenes' own chapters are NOT merged in. They describe structure
    inside one scene, detected from its audio; a compilation's chapters are
    the joins the author made. Keeping both would mean two competing
    boundary sets in one file.
    """
    from .chapters import build_chapters

    chapters = [
        {
            "at_ms": c.start_ms,
            "end_ms": c.end_ms,
            "name": c.name or "",
            "intent": "",
            # Authored, not inferred from audio — say so rather than claiming
            # a detector's confidence.
            "source": "forgeassembler.sections",
        }
        for c in build_chapters(project, layout)
    ]
    return {
        "version": "3.0",
        "schema": "audio-structure",
        "chapters": chapters,
        "auto_generated": False,
        "generated_by": {
            "tool": "forgeassembler.chapters",
            "method": "section-boundaries",
        },
    }


# ── joining the analysis sidecars ────────────────────────────────────
def _segment_windows(project: "Project", layout: "Layout") -> list[tuple]:
    """Every segment as `(segment, timeline_start_ms, trim_start_ms, duration_ms)`.

    The trim is what makes this more than an offset: a clip contributes only
    the window the author kept, so a sidecar sample has to be taken from
    `trim_start + x` in the SOURCE and laid down at `timeline_start + x`.
    """
    out = []
    for li in layout.items:
        if not li.is_segment:
            continue
        seg = li.item
        out.append((seg, li.start_ms, seg.trim_start_ms(), li.duration_ms))
    return out


def _load_sidecar(seg, name: str) -> Optional[dict]:
    """Read one analysis sidecar off a segment, or None if it has none."""
    raw = (seg.sidecars or {}).get(name)
    if not raw:
        return None
    try:
        data = json.loads(Path(raw).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def join_beats(project: "Project", layout: "Layout") -> Optional[dict]:
    """Join the input scenes' `beats.json` onto the compilation's timeline.

    Each scene's beat times are shifted to where that clip actually plays and
    clipped to its trim window, so the beats of a clip that starts 40 minutes
    in land 40 minutes in. A clip with no beats sidecar simply contributes
    none — the result is honest about being partial rather than inventing
    beats for it.

    Returns None when no clip carries beats, so the caller writes no file
    instead of an empty one.
    """
    beats: list[int] = []
    downbeats: list[int] = []
    carried = 0
    for seg, start_ms, trim_ms, dur_ms in _segment_windows(project, layout):
        data = _load_sidecar(seg, "beats")
        if not data:
            continue
        carried += 1
        for key, dest in (("beats_ms", beats), ("downbeats_ms", downbeats)):
            for raw in data.get(key) or []:
                try:
                    at = int(raw)
                except (TypeError, ValueError):
                    continue
                shifted = at - trim_ms
                if 0 <= shifted < dur_ms:
                    dest.append(start_ms + shifted)
    if not carried or not beats:
        return None
    beats.sort()
    downbeats.sort()
    total = layout.total_duration_ms
    # BPM over the whole compilation. Scenes at different tempos average out,
    # which is the only meaningful single number for a joined file.
    bpm = (len(beats) * 60000.0 / total) if total else 0.0
    return {
        "version": "1.0",
        "duration_ms": total,
        "bpm": bpm,
        "beats_ms": beats,
        "downbeats_ms": downbeats,
        "generated_by": {
            "tool": "forgeassembler.join",
            "method": "shift+concat of source beats.json",
            "clips_with_beats": carried,
        },
    }


def _peaks_at_hop(data: dict) -> Optional[tuple[list, int]]:
    """`(peaks, hop_ms)` from an `audio.json`, or None if unusable."""
    peaks = data.get("peaks")
    if not isinstance(peaks, list) or not peaks:
        return None
    try:
        hop = int(data.get("hop_ms") or 0)
    except (TypeError, ValueError):
        return None
    return (peaks, hop) if hop > 0 else None


def join_audio_peaks(project: "Project", layout: "Layout") -> Optional[dict]:
    """Join the input scenes' `audio.json` waveform peaks onto the timeline.

    Peaks are a fixed-hop array, so joining is a resample-and-splice: take
    each clip's trim window, lay it down at the clip's start, and leave zeros
    wherever no clip supplied samples — a joiner's black hold, or a clip whose
    scene shipped no waveform. Zeros are honest here: they are what silence
    looks like in this format, and the alternative (omitting the file) would
    make every consumer decode a multi-hour video to draw one lane.

    A scene at a different hop is resampled by nearest sample rather than
    dropped, since mixing 10 ms and 20 ms sources is otherwise fatal to the
    whole lane.
    """
    total = layout.total_duration_ms
    if total <= 0:
        return None
    windows = _segment_windows(project, layout)
    loaded = [
        (seg, start, trim, dur, _peaks_at_hop(data))
        for seg, start, trim, dur in windows
        for data in [_load_sidecar(seg, "audio") or {}]
    ]
    if not any(p for *_rest, p in loaded):
        return None

    count = total // _PEAK_HOP_MS + 1
    out = [0.0] * count
    carried = 0
    for _seg, start_ms, trim_ms, dur_ms, got in loaded:
        if not got:
            continue
        carried += 1
        peaks, hop = got
        for i in range(dur_ms // _PEAK_HOP_MS + 1):
            dest = (start_ms + i * _PEAK_HOP_MS) // _PEAK_HOP_MS
            if not 0 <= dest < count:
                continue
            src = (trim_ms + i * _PEAK_HOP_MS) // hop
            if 0 <= src < len(peaks):
                try:
                    out[dest] = float(peaks[src])
                except (TypeError, ValueError):
                    pass
    return {
        "version": "1.0",
        "hop_ms": _PEAK_HOP_MS,
        "duration_ms": total,
        "peaks": out,
        "peak_count": len(out),
        "generated_by": {
            "tool": "forgeassembler.join",
            "method": "resample+splice of source audio.json",
            "clips_with_peaks": carried,
        },
    }


# ── lineage ──────────────────────────────────────────────────────────
def _source_scenes(project: "Project") -> list[dict]:
    """What went into this compilation, in order, for the manifest.

    Only the assembler knows this, and it is the first thing anyone asks of a
    long joined file. A clip that came from a `.forge` scene contributes its
    bookmark; a plain video contributes its filename.
    """
    from .project import Segment as _Seg

    scenes = []
    for section in project.sections:
        for item in section.segments:
            if not isinstance(item, _Seg) or item.is_still():
                continue
            scenes.append({
                "name": item.bookmark or Path(item.video).stem,
                "video": Path(item.video).name,
            })
    return scenes


def _project_id(project: "Project") -> str:
    """A stable id for this compilation.

    Derived from the output name and the ordered source list, so re-forging
    the same compilation keeps its lineage while a different one gets its own
    id. FunscriptForge persists this in the working folder; a ForgeAssembler
    project has no such folder, and deriving it beats writing to the user's
    project file behind their back during a forge.
    """
    basis = "|".join(
        [project.output.basename or "combined"]
        + [s["name"] for s in _source_scenes(project)]
    )
    return hashlib.md5(basis.encode("utf-8")).hexdigest()  # noqa: S324


# ── the writer ───────────────────────────────────────────────────────
def write_forge_bundle(
    project: "Project",
    layout: "Layout",
    out_path: str | Path,
    *,
    funscripts: Optional[dict[str, Path]] = None,
    audio: Optional[Iterable[Path]] = None,
    video: Optional[str | Path] = None,
    thumbnails: Optional[dict[str, Path]] = None,
    include_media: bool = False,
    stem: Optional[str] = None,
    now: Optional[int] = None,
) -> Path:
    """Package a forged compilation as a `.forge` bundle at `out_path`.

    Everything is optional because a forge is: someone can produce funscripts
    with no video, or a video with `--no-funscripts`. Whatever was written
    goes in, and the manifest describes exactly that — no placeholder entries
    for artifacts that do not exist.

    `funscripts` is `{channel key: path}` from `forge_funscripts_map`; the
    keys are what place each file under its station. `audio` is the list of
    joined audio files. Returns the bundle path.
    """
    from .project import Segment as _Seg  # noqa: F401  (kept for parity)

    out_path = Path(out_path)
    stem = stem or project.output.basename or "combined"
    staging = Path(tempfile.mkdtemp(prefix="fa-forge-"))
    try:
        artifacts: list[dict] = []
        stations_meta: dict[str, dict] = {}

        # 1. funscripts — motion at the root, everything else by station.
        for key, src in sorted((funscripts or {}).items()):
            src = Path(src)
            if not src.is_file():
                continue
            rel = bundle_relpath(key, stem)
            dest = staging / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            if rel == MOTION_NAME:
                artifacts.append({"path": rel, "kind": "funscript",
                                  "role": "stroke", "axis": "L0"})
                continue
            station = station_of(key) or with_station(key)[0]
            art = {"path": rel, "kind": "funscript", "role": "device"}
            if station:
                art["station"] = station
                stations_meta.setdefault(station, {"files": []})
                stations_meta[station]["files"].append(Path(rel).name)
            artifacts.append(art)

        # 2. haptic audio — by role, under `audio/`, as FunscriptForge names it.
        for src in audio or []:
            src = Path(src)
            if not src.is_file():
                continue
            channel = _audio_channel_of(src, stem)
            role, base = AUDIO_ROLE_FOR_CHANNEL.get(
                channel, (channel or "audio", Path(channel or src.stem).stem))
            fmt = src.suffix.lstrip(".").lower()
            rel = f"audio/{base}.{fmt}"
            dest = staging / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            artifacts.append({"path": rel, "kind": "audio",
                              "role": role, "format": fmt})

        # 3. analysis — the compilation's chapters, plus the joined sidecars.
        #    These are what let the next tool open a two-hour file quickly
        #    instead of decoding it to draw a waveform.
        for name, data in (
            ("chapters", compilation_chapters(project, layout)),
            ("beats", join_beats(project, layout)),
            ("audio", join_audio_peaks(project, layout)),
        ):
            if not data:
                continue
            (staging / f"{name}.json").write_text(
                json.dumps(data), encoding="utf-8")
            artifacts.append({"path": f"{name}.json", "kind": "sidecar",
                              "analysis": name})

        # 4. thumbnails, when the caller extracted any.
        for role, src in sorted((thumbnails or {}).items()):
            src = Path(src)
            if not src.is_file():
                continue
            rel = f"thumbnails/{src.name}"
            dest = staging / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            art = {"path": rel, "kind": "thumbnail", "role": role.split("_")[0]}
            if role.startswith("chapter_"):
                try:
                    art["index"] = int(role.split("_", 1)[1])
                except ValueError:
                    pass
            artifacts.append(art)

        # 5. the combined video — provenance always, bytes only on request.
        media_meta = None
        if video and Path(video).exists():
            media_meta = media_provenance(Path(video))
            if include_media:
                rel = f"media/{media_meta['filename']}"
                dest = staging / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(video, dest)
                media_meta["bundled"] = True
                media_meta["path"] = rel
                artifacts.append({"path": rel, "kind": "media", "role": "source"})
            else:
                media_meta["bundled"] = False

        # 6. manifest.
        import datetime as _dt

        manifest = {
            "version": 1,
            "schema": "ffmeta/v1",
            "stem": stem,
            "created_with": "ForgeAssembler",
            "duration_ms": layout.total_duration_ms,
            "project_id": _project_id(project),
            # Not a counter: a ForgeAssembler project has no working folder to
            # keep one in, and a version that never moved would let a consumer
            # caching on (id, version) serve a stale extraction after a
            # re-forge. Seconds since the epoch always moves forward.
            "project_version": int(now if now is not None else time.time()),
            "exported_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "artifacts": artifacts,
            "stations": stations_meta,
            # ForgeAssembler's own addition: what this was joined FROM.
            "compilation": {
                "sections": len(project.sections),
                "scenes": _source_scenes(project),
            },
        }
        if media_meta:
            manifest["media"] = media_meta
        (staging / MANIFEST_NAME).write_text(
            json.dumps(manifest, indent=2), encoding="utf-8")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
            for fp in sorted(staging.rglob("*")):
                if fp.is_file():
                    z.write(fp, fp.relative_to(staging).as_posix())
        return out_path
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _audio_channel_of(path: Path, stem: str) -> str:
    """Recover the engine's audio channel key from a written filename.

    `forge_audio_estim` writes `<stem>.<channel>` where the channel already
    carries its extension (`prostate.mp3`), so the channel is whatever
    follows the stem.
    """
    name = path.name
    prefix = f"{stem}."
    return name[len(prefix):] if name.startswith(prefix) else name
