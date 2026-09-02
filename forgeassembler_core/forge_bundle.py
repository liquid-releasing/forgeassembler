# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Import a FunscriptForge `.forge` bundle as a forgeassembler Segment.

A `.forge` bundle is a ZIP (named `<stem>.forge`) produced by FunscriptForge's
`cli.py export --mode forge`. It contains a `manifest.ffmeta` (JSON) plus the
artifacts it describes:

    manifest.ffmeta
    motion.funscript                       # the main stroke track (axis L0)
    stations/<id>/<stem>.<channel>.funscript   # device channels (estim3p, tcode, …)
    thumbnails/…                           # preview PNGs
    media/<file>                           # only when exported --include-media

The manifest's `artifacts` list is authoritative — every funscript (motion +
every station file) is listed there with its `kind`/`role`/`axis`, so a single
pass over `artifacts` maps the whole bundle. One finished FunscriptForge scene
becomes one assembler Segment.

This is the clean replacement for sibling-funscript discovery: the manifest
declares the channel list instead of us guessing by stem.

Naming-collision note: forgeassembler ALSO has a `.forge/` notion — a working
folder TREE of numbered subdirs (`.forge/0/`, `.forge/1/`) scanned by
`detect_folder_tree`. Those are DIRECTORIES; a FunscriptForge bundle is a
single `.forge` FILE (a zip). `is_forge_bundle()` distinguishes them so the two
never cross.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .detect import _split_ff_suffix
from .project import Segment, new_id

MANIFEST_NAME = "manifest.ffmeta"
MOTION_NAME = "motion.funscript"

__all__ = [
    "ForgeBundle",
    "is_forge_bundle",
    "detect_forge_bundle",
    "forge_bundle_to_segment",
]


@dataclass
class ForgeBundle:
    """The unpacked result of a `.forge` bundle — manifest + extracted paths.

    `video` resolution is deliberately separate (see `media_path`): a lean
    bundle carries no media, so the Segment can't be built until a video is
    relinked. `forge_bundle_to_segment(bundle, video=…)` does that step.
    """

    path: Path                                    # the source .forge file
    cache_dir: Path                               # where it was extracted
    manifest: dict
    stem: str
    funscripts: dict[str, Path] = field(default_factory=dict)   # channel -> path
    audio_estim: dict[str, Path] = field(default_factory=dict)  # channel key -> path
    sidecars: dict[str, Path] = field(default_factory=dict)     # analysis -> path
    thumbnails: dict[str, Path] = field(default_factory=dict)   # role -> path
    media: Optional[dict] = None                  # manifest `media` block, if any
    media_path: Optional[Path] = None             # resolved video, else None

    @property
    def project_id(self) -> Optional[str]:
        return self.manifest.get("project_id")

    @property
    def project_version(self):
        return self.manifest.get("project_version")

    @property
    def duration_ms(self):
        return self.manifest.get("duration_ms")

    @property
    def channels(self) -> list[str]:
        return list(self.funscripts.keys())


def is_forge_bundle(path: str | Path) -> bool:
    """True only for a FunscriptForge `.forge` bundle: a `.forge` FILE that is
    a real zip. A `.forge` directory (the working-folder tree) and the legacy
    JSON `.forge` descriptor both return False."""
    p = Path(path)
    return p.is_file() and p.suffix.lower() == ".forge" and zipfile.is_zipfile(p)


def _read_manifest_from_zip(p: Path) -> dict:
    with zipfile.ZipFile(p) as z:
        if MANIFEST_NAME not in z.namelist():
            raise ValueError(f"bundle missing {MANIFEST_NAME}: {p}")
        return json.loads(z.read(MANIFEST_NAME).decode("utf-8"))


# Records which .forge file an extraction came from. The cache key alone
# (project_id + version) cannot tell a re-export apart from the export it
# replaced — FunscriptForge does not have to bump project_version to write
# new contents — so a stale cache would quietly outrank the bundle. The
# `.forge` file is the source of truth about a clip; this stamp is what
# keeps that true.
def forge_bundles_in(folder: str | Path) -> list[Path]:
    """Every `.forge` bundle directly inside `folder`, name-sorted.

    Deliberately shallow and cheap: no zip is opened, so a folder of 50
    scenes lists instantly and the caller decides which to actually
    import. Sorted so "Add folder" produces the same section order every
    time (vol 1, vol 2, ...).
    """
    d = Path(folder)
    if not d.is_dir():
        raise NotADirectoryError(d)
    return sorted(
        (f for f in d.iterdir() if f.is_file() and f.suffix.lower() == ".forge"),
        key=lambda f: f.name.lower(),
    )


SOURCE_STAMP_NAME = ".source.json"


def _zip_fingerprint(bundle_path: Path) -> str:
    """A content fingerprint of the bundle, from its zip CENTRAL DIRECTORY.

    Every member's name, CRC-32 and uncompressed size — read from the
    directory at the end of the file, so nothing is decompressed and a
    20 MB bundle fingerprints in milliseconds.

    Size + mtime alone is NOT enough. FunscriptForge can re-export a
    scene whose zip is byte-for-byte the same LENGTH (an action changing
    from `"pos":10` to `"pos":99` costs no bytes), and if that lands in
    the same filesystem timestamp tick — Windows timestamps are coarse —
    the cache looks fresh and hands back the PREVIOUS export. That is the
    "I fixed it and nothing changed" failure this stamp exists to stop.
    """
    h = hashlib.sha256()
    try:
        with zipfile.ZipFile(bundle_path) as z:
            for info in z.infolist():
                # Separators are plain ASCII so the fingerprint is easy to
                # eyeball in a stamp file; they only need to be characters a
                # member name can't contain unescaped.
                h.update(info.filename.encode("utf-8", "replace"))
                h.update(b"|")
                h.update(str(info.CRC).encode("ascii"))
                h.update(b"|")
                h.update(str(info.file_size).encode("ascii"))
                h.update(b";")
    except (OSError, zipfile.BadZipFile):
        # Unreadable here means unreadable everywhere downstream; return a
        # value that never matches so the cache is treated as stale.
        return "unreadable"
    return h.hexdigest()


def _source_stamp(bundle_path: Path) -> dict:
    st = bundle_path.stat()
    return {
        "path": str(bundle_path),
        "size": st.st_size,
        "mtime_ns": st.st_mtime_ns,
        "fingerprint": _zip_fingerprint(bundle_path),
    }


def _cache_is_fresh(cache_dir: Path, bundle_path: Path) -> bool:
    """True when `cache_dir` holds this exact bundle, already extracted."""
    if not (cache_dir / MANIFEST_NAME).is_file():
        return False
    try:
        stamped = json.loads((cache_dir / SOURCE_STAMP_NAME).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # Extracted by an older build that wrote no stamp — re-extract once
        # rather than trust it.
        return False
    fresh = _source_stamp(bundle_path)
    # An older stamp has no fingerprint; re-extract once to gain one rather
    # than trusting size+mtime, which is what let a stale export through.
    if "fingerprint" not in stamped:
        return False
    return stamped == fresh


def _cache_dir_for(manifest: dict, cache_root: Path) -> Path:
    """Stable per-bundle cache key from the project lineage so re-importing the
    same exported snapshot doesn't re-extract."""
    pid = str(manifest.get("project_id") or "noid")
    ver = manifest.get("project_version")
    ver = int(ver) if ver is not None else 0
    return cache_root / f"{pid}.v{ver}"


# Manifest audio `role` -> the engine's channel key. The engine names
# channels after the FILENAME suffix a sibling would have had
# (`<stem>.mp3` -> "mp3", `<stem>.prostate.mp3` -> "prostate.mp3"), and
# names its outputs the same way, so a bundle's audio has to arrive under
# those keys or the combined output would be named after a bundle-internal
# role nobody else uses.
_AUDIO_ROLE_SUFFIX: dict[str, str] = {
    "estim": "",                    # the main haptic track -> `<basename>.mp3`
    "estim-prostate": "prostate",   #                       -> `<basename>.prostate.mp3`
}


def _channel_for_audio(rel_path: str, artifact: dict) -> str:
    """Map an audio artifact to the engine's channel key.

    Unknown roles pass through under their own name rather than being
    dropped — a new FunscriptForge audio role should show up as an extra
    output channel, not vanish silently.
    """
    ext = (artifact.get("format") or Path(rel_path).suffix.lstrip(".") or "mp3").lower()
    role = artifact.get("role") or Path(rel_path).stem
    suffix = _AUDIO_ROLE_SUFFIX.get(role, role)
    return f"{suffix}.{ext}" if suffix else ext


def _channel_for_funscript(rel_path: str, artifact: dict) -> str:
    """Map an artifact's relative path to a channel key.

    `motion.funscript` (axis L0) is the main stroke track. Station files are
    named `<stem>.<channel>.funscript`, so the trailing FF suffix IS the
    channel (alpha, beta, e1..e4, surge, sway, pulse_frequency,
    alpha-prostate, …)."""
    name = Path(rel_path).name
    if name == MOTION_NAME or artifact.get("axis") == "L0":
        return "main"
    _base, channel = _split_ff_suffix(name)
    return channel or "main"


def _map_artifacts(
    manifest: dict, cache_dir: Path,
) -> tuple[dict[str, Path], dict[str, Path], dict[str, Path], dict[str, Path]]:
    """Sort every manifest artifact into funscripts, audio, analysis
    sidecars and thumbnails — all keyed the way consumers ask for them."""
    funscripts: dict[str, Path] = {}
    audio_estim: dict[str, Path] = {}
    sidecars: dict[str, Path] = {}
    thumbnails: dict[str, Path] = {}
    for art in manifest.get("artifacts", []):
        rel = art.get("path")
        if not rel:
            continue
        kind = art.get("kind")
        fp = cache_dir / rel
        if kind == "funscript":
            channel = _channel_for_funscript(rel, art)
            # First artifact for a channel wins (motion before stations in the
            # manifest); deterministic.
            funscripts.setdefault(channel, fp)
        elif kind in ("audio", "audio_estim", "stim_audio"):
            audio_estim.setdefault(_channel_for_audio(rel, art), fp)
        elif kind == "sidecar":
            # `analysis` names it: audio (waveform peaks), beats, chapters,
            # phrases, characters. These are what let a preview open fast
            # instead of decoding the whole video again.
            sidecars.setdefault(art.get("analysis") or Path(rel).stem, fp)
        elif kind == "thumbnail":
            role = art.get("role") or Path(rel).stem
            if role == "chapter" and art.get("index") is not None:
                role = f"chapter_{art['index']}"
            thumbnails.setdefault(role, fp)
    return funscripts, audio_estim, sidecars, thumbnails


def _resolve_media(
    bundle_path: Path,
    cache_dir: Path,
    media: Optional[dict],
    media_roots: Optional[list[Path]],
) -> Optional[Path]:
    """Resolve the source video for a bundle, or None when it can't be found.

    Order: (1) media bundled inside the zip (`--include-media`); (2) a file
    matching `media.filename` next to the bundle or under a configured root.
    Validation against `media.size` keeps it cheap; the heavy `head_sha256`
    check is left to the caller's relink UX.
    """
    if not media:
        return None
    # 1. Bundled media.
    if media.get("bundled"):
        rel = media.get("path") or (f"media/{media.get('filename')}" if media.get("filename") else None)
        if rel:
            cand = cache_dir / rel
            if cand.is_file():
                return cand
    # 2. Resolve the original on disk by filename.
    filename = media.get("filename")
    if not filename:
        return None
    search = [bundle_path.parent, *(media_roots or [])]
    want_size = media.get("size")
    for root in search:
        cand = Path(root) / filename
        if cand.is_file():
            if want_size is None or cand.stat().st_size == want_size:
                return cand
    return None


def detect_forge_bundle(
    path: str | Path,
    cache_root: Optional[str | Path] = None,
    media_roots: Optional[list[str | Path]] = None,
) -> ForgeBundle:
    """Unpack a `.forge` bundle to a cache dir and map its manifest.

    Idempotent: a bundle already extracted (same project_id + version) is
    reused rather than re-unzipped.
    """
    p = Path(path).resolve()
    if not is_forge_bundle(p):
        raise ValueError(f"not a .forge bundle (expected a .forge zip file): {p}")

    manifest = _read_manifest_from_zip(p)
    root = Path(cache_root) if cache_root else Path(tempfile.gettempdir()) / "forgeassembler_bundles"
    cache_dir = _cache_dir_for(manifest, root)

    if not _cache_is_fresh(cache_dir, p):
        # Clear it out first: a re-export can drop artifacts as well as add
        # them, and extracting over the top would leave the deleted ones
        # lying around to be mapped as though they were still current.
        if cache_dir.exists():
            shutil.rmtree(cache_dir, ignore_errors=True)
        cache_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(p) as z:
            # Trusted FunscriptForge output; guard against path escape anyway.
            for member in z.namelist():
                dest = (cache_dir / member).resolve()
                if not str(dest).startswith(str(cache_dir.resolve())):
                    raise ValueError(f"unsafe path in bundle: {member}")
            z.extractall(cache_dir)
        (cache_dir / SOURCE_STAMP_NAME).write_text(
            json.dumps(_source_stamp(p)), encoding="utf-8",
        )

    # Re-read from the extracted copy (authoritative on disk).
    manifest = json.loads((cache_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
    stem = manifest.get("stem") or p.stem
    funscripts, audio_estim, sidecars, thumbnails = _map_artifacts(manifest, cache_dir)
    media = manifest.get("media")
    media_path = _resolve_media(
        p, cache_dir, media,
        [Path(r) for r in media_roots] if media_roots else None,
    )
    return ForgeBundle(
        path=p, cache_dir=cache_dir, manifest=manifest, stem=stem,
        funscripts=funscripts, audio_estim=audio_estim,
        sidecars=sidecars, thumbnails=thumbnails,
        media=media, media_path=media_path,
    )


def forge_bundle_to_segment(
    bundle: ForgeBundle,
    video: Optional[str | Path] = None,
    seg_id: Optional[str] = None,
) -> Segment:
    """Build one explicit-funscript Segment from a bundle.

    `video` relinks the source clip; when omitted the bundle's resolved
    `media_path` is used. Raises if neither is available (the assembler can't
    concat without frames).
    """
    vid = video or bundle.media_path
    if not vid:
        raise ValueError(
            f"forge bundle '{bundle.stem}' has no resolvable video; "
            "pass video= to relink the source clip"
        )
    explicit = {ch: str(p) for ch, p in bundle.funscripts.items()}
    return Segment(
        id=seg_id or new_id("seg"),
        video=str(vid),
        funscripts_source="explicit",
        explicit_funscripts=explicit,
        # The bundle's own stim audio. Without this the forge falls back to
        # scanning for `.stereostim.wav` siblings of the video, finds none,
        # and writes no haptic audio at all — while the files sat unused in
        # the extraction cache.
        explicit_audio_estim={ch: str(p) for ch, p in bundle.audio_estim.items()},
        bookmark=bundle.stem,
    )
