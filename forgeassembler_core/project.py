# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Project data model + JSON load/save/validate.

v2.0 model: a Project owns a list of **Sections**; each Section has a
**leading joiner** (how it transitions IN from the previous section,
default "none" = hard cut) and a list of **segments** (video / still
clips joined with straight cuts within the section). Fades /
fade-to-black live at section boundaries only — no mid-section
transitions. Old `items`-format projects (PROJECT_VERSION "1.0") are
auto-migrated on load.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

PROJECT_VERSION = "2.0"

AudioMode = Literal["keep", "replace", "silence"]
JoinerType = Literal["none", "fade_to_black"]
OverlayType = Literal["image", "text"]
BugCorner = Literal["tl", "tr", "bl", "br"]
SegmentBackground = Literal["black", "previous_last_frame"]
Quality = Literal["high", "medium", "low"]
FrameRate = Literal["source", "24", "30", "60"]

# Section-level overlay positions. "center" plus the four corners
# match the `BugCorner` set with a center option.
OverlayPosition = Literal["center", "tl", "tr", "bl", "br"]
SectionOverlayKind = Literal["image", "audio", "text"]

OVERLAY_POSITIONS: tuple[str, ...] = (
    # 3×3 grid ordered top-row, middle-row, bottom-row for readable
    # dropdowns. "center" is the vertical-and-horizontal center.
    "tl", "tc", "tr",
    "ml", "center", "mr",
    "bl", "bc", "br",
)

# Keys for the Frame rate dropdown. "source" probes the first video
# segment at forge time (via ffmpeg stderr) and mirrors its fps; this
# avoids the `drop=N` frame-drop artefact you get when forcing a 60fps
# source down to 30fps on encode.
FRAME_RATE_KEYS: tuple[str, ...] = ("source", "24", "30", "60")

# Map each quality preset to an H.264 CRF value. Lower CRF = higher
# quality = bigger file. 18-28 is a sensible span for 1080p x264.
QUALITY_CRF: dict[str, int] = {
    "high": 18,      # archive / re-edit (~10 Mbps 1080p)
    "medium": 23,    # YouTube-friendly default (~4 Mbps 1080p)
    "low": 28,       # Discord / draft (~2 Mbps 1080p)
}

# Output resolutions the forge pipeline accepts. "source" defers to
# ffprobe on the first segment at forge time.
RESOLUTION_KEYS: tuple[str, ...] = (
    "1080p", "1440p", "4k",
    "uw_1080p", "uw_1440p",
    "4_3_hd", "3_4_hd", "9_16_hd",
    "source",
)

RESOLUTION_PIXELS: dict[str, Optional[tuple[int, int]]] = {
    "1080p": (1920, 1080),
    "1440p": (2560, 1440),
    "4k": (3840, 2160),
    "uw_1080p": (2560, 1080),
    "uw_1440p": (3440, 1440),
    "4_3_hd": (1440, 1080),
    "3_4_hd": (1080, 1440),
    "9_16_hd": (1080, 1920),
    "source": None,
}

STILL_IMAGE_EXTENSIONS: frozenset[str] = frozenset({
    ".png", ".jpg", ".jpeg", ".webp",
})


def is_still_image(path: str | Path) -> bool:
    """True if the given path names a still image (by extension)."""
    return Path(path).suffix.lower() in STILL_IMAGE_EXTENSIONS


# Matches a trailing `_<10+digit timestamp>` optionally followed by
# `_<alphanumeric suffix>` — the XBVR/download-tool "uniqueness" pattern
# like `_1771804425489_ahmyeutv`.
_FILENAME_SUFFIX_RE = re.compile(r"_\d{10,}(_[a-zA-Z0-9]+)?$")


def prettify_filename_stem(stem: str) -> str:
    """Turn a video-filename stem into a human-readable chapter title.

    - strip trailing `_<timestamp>` or `_<timestamp>_<hash>` uniqueness suffix
    - replace `_` with spaces
    - collapse runs of whitespace

    Example: `VictoriaOaks_-_MilaRuby_PMV3_Gooning_Therapy_1771804425489_ahmyeutv`
    → `VictoriaOaks - MilaRuby PMV3 Gooning Therapy`.
    """
    cleaned = _FILENAME_SUFFIX_RE.sub("", stem)
    cleaned = cleaned.replace("_", " ")
    return re.sub(r"\s+", " ", cleaned).strip()


# ── Time-format helpers (HH:MM:SS.mmm <-> ms) ─────────────────────────
def parse_hms_ms(text: str) -> int:
    """Parse a HH:MM:SS.mmm / MM:SS.mmm / SS.mmm timestamp into ms.

    Accepts any of:
      "HH:MM:SS"        e.g. "01:23:45"
      "HH:MM:SS.mmm"    e.g. "01:23:45.678"
      "MM:SS"           e.g. "23:45"
      "MM:SS.mmm"       e.g. "23:45.678"
      "SS"              e.g. "45"
      "SS.mmm"          e.g. "45.678"

    Empty / whitespace-only input raises ValueError. Negative results
    are also a ValueError (no "-1.5" — use 0 to mean "from start").
    """
    s = text.strip()
    if not s:
        raise ValueError("empty timestamp")
    parts = s.split(":")
    if len(parts) > 3:
        raise ValueError(f"too many ':' in timestamp: {text!r}")
    try:
        if len(parts) == 3:
            h, m, sec = int(parts[0]), int(parts[1]), float(parts[2])
        elif len(parts) == 2:
            h, m, sec = 0, int(parts[0]), float(parts[1])
        else:
            h, m, sec = 0, 0, float(parts[0])
    except ValueError as exc:
        raise ValueError(f"could not parse timestamp {text!r}: {exc}") from exc
    if h < 0 or m < 0 or sec < 0:
        raise ValueError(f"timestamp must be non-negative: {text!r}")
    if m >= 60 or sec >= 60:
        raise ValueError(
            f"minutes and seconds must each be < 60: {text!r}",
        )
    total_ms = ((h * 3600) + (m * 60)) * 1000 + int(round(sec * 1000))
    return total_ms


def format_hms_ms(ms: int) -> str:
    """Format a non-negative ms value as `HH:MM:SS.mmm`.

    Always pads to the full HH:MM:SS.mmm shape for UI consistency, so
    a list of timestamps lines up visually regardless of magnitude.
    """
    if ms < 0:
        raise ValueError(f"ms must be non-negative: {ms}")
    total_seconds, millis = divmod(ms, 1000)
    h, rem = divmod(total_seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}.{millis:03d}"


# ── Layers ────────────────────────────────────────────────────────────
@dataclass
class AudioLayer:
    mode: AudioMode = "keep"
    file: Optional[str] = None  # required when mode == "replace"

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"mode": self.mode}
        if self.file:
            d["file"] = self.file
        return d

    @staticmethod
    def from_dict(d: dict | None) -> "AudioLayer":
        if not d:
            return AudioLayer()
        return AudioLayer(mode=d.get("mode", "keep"), file=d.get("file"))


@dataclass
class Overlay:
    type: OverlayType
    # Image overlay
    file: Optional[str] = None
    # Text overlay
    content: Optional[str] = None
    font: Optional[str] = None
    size: int = 72
    color: str = "#ffffff"
    outline_color: str = "#000000"
    outline_width: int = 0
    # Common
    position: str = "center"
    start_s: float = 0.0
    end_s: Optional[float] = None
    fade_in_s: float = 0.0
    fade_out_s: float = 0.0
    opacity: float = 1.0

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "type": self.type,
            "position": self.position,
            "start_s": self.start_s,
            "fade_in_s": self.fade_in_s,
            "fade_out_s": self.fade_out_s,
            "opacity": self.opacity,
        }
        if self.end_s is not None:
            d["end_s"] = self.end_s
        if self.type == "image":
            d["file"] = self.file
        else:
            d.update({
                "content": self.content,
                "font": self.font,
                "size": self.size,
                "color": self.color,
                "outline_color": self.outline_color,
                "outline_width": self.outline_width,
            })
        return d

    @staticmethod
    def from_dict(d: dict) -> "Overlay":
        return Overlay(
            type=d["type"],
            file=d.get("file"),
            content=d.get("content"),
            font=d.get("font"),
            size=d.get("size", 72),
            color=d.get("color", "#ffffff"),
            outline_color=d.get("outline_color", "#000000"),
            outline_width=d.get("outline_width", 0),
            position=d.get("position", "center"),
            start_s=d.get("start_s", 0.0),
            end_s=d.get("end_s"),
            fade_in_s=d.get("fade_in_s", 0.0),
            fade_out_s=d.get("fade_out_s", 0.0),
            opacity=d.get("opacity", 1.0),
        )


# ── Project-level branding / bug overlay ──────────────────────────────
@dataclass
class BugOverlay:
    """A PNG composited into a corner of every segment's video."""
    file: str
    corner: BugCorner = "br"
    margin_px: int = 24
    opacity: float = 1.0

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "corner": self.corner,
            "margin_px": self.margin_px,
            "opacity": self.opacity,
        }

    @staticmethod
    def from_dict(d: dict) -> "BugOverlay":
        return BugOverlay(
            file=d["file"],
            corner=d.get("corner", "br"),
            margin_px=int(d.get("margin_px", 24)),
            opacity=float(d.get("opacity", 1.0)),
        )


# ── Project-level output settings ─────────────────────────────────────
@dataclass
class Metadata:
    """MP4 container metadata embedded in the forged output.

    These travel with the file. Players surface them in different
    places — VLC briefly overlays `title` on playback, File Explorer
    lists them in Properties, Plex/Jellyfin read them for library
    cards, YouTube reads `title` as the upload title.
    """
    title: Optional[str] = None
    artist: Optional[str] = None
    date: Optional[str] = None   # e.g. "2026-04-19" or "2026"
    genre: Optional[str] = None
    comment: Optional[str] = None
    copyright: Optional[str] = None

    def to_dict(self) -> dict:
        # Only serialize non-empty fields so JSON stays clean.
        d: dict[str, Any] = {}
        for key in ("title", "artist", "date", "genre", "comment", "copyright"):
            value = getattr(self, key)
            if value:
                d[key] = value
        return d

    @staticmethod
    def from_dict(d: dict | None) -> "Metadata":
        if not d:
            return Metadata()
        return Metadata(
            title=d.get("title"),
            artist=d.get("artist"),
            date=d.get("date"),
            genre=d.get("genre"),
            comment=d.get("comment"),
            copyright=d.get("copyright"),
        )

    def non_empty_items(self) -> list[tuple[str, str]]:
        """Return (key, value) pairs for every non-empty field, suitable
        for rendering as ffmpeg `-metadata key=value` pairs."""
        return [
            (k, v) for k, v in (
                ("title", self.title),
                ("artist", self.artist),
                ("date", self.date),
                ("genre", self.genre),
                ("comment", self.comment),
                ("copyright", self.copyright),
            ) if v
        ]


@dataclass
class Output:
    """Project-level output configuration (resolution, audio, toggles, bug)."""
    folder: Optional[str] = None
    basename: str = "combined"
    resolution: str = "1080p"
    quality: str = "medium"
    frame_rate: str = "source"
    normalize_audio: bool = True
    produce_video: bool = True
    produce_funscripts: bool = True
    bug: Optional[BugOverlay] = None
    metadata: Metadata = field(default_factory=Metadata)
    # Closing transition for the whole output. When `closing_joiner` is
    # "fade_to_black", the engine fades the final video (and audio) to
    # black/silence in the last `duration_s` seconds of the output.
    # Default "none" = hard end, no fade.
    closing_joiner: "Joiner" = field(default_factory=lambda: Joiner(
        id="join-close", joiner_type="none",
    ))

    def crf(self) -> int:
        """Return the H.264 CRF value implied by `quality`."""
        return QUALITY_CRF.get(self.quality, QUALITY_CRF["medium"])

    def fps(self) -> Optional[int]:
        """Return the integer fps implied by `frame_rate`, or None when
        the caller must probe the first segment (`frame_rate == 'source'`)."""
        if self.frame_rate == "source":
            return None
        try:
            return int(self.frame_rate)
        except ValueError:
            return None

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "folder": self.folder,
            "basename": self.basename,
            "resolution": self.resolution,
            "quality": self.quality,
            "frame_rate": self.frame_rate,
            "normalize_audio": self.normalize_audio,
            "produce_video": self.produce_video,
            "produce_funscripts": self.produce_funscripts,
        }
        if self.bug is not None:
            d["bug"] = self.bug.to_dict()
        md = self.metadata.to_dict()
        if md:
            d["metadata"] = md
        if self.closing_joiner.joiner_type != "none":
            d["closing_joiner"] = self.closing_joiner.to_dict()
        return d

    @staticmethod
    def from_dict(d: dict | None) -> "Output":
        if not d:
            return Output()
        bug_dict = d.get("bug")
        closing_dict = d.get("closing_joiner")
        return Output(
            folder=d.get("folder"),
            basename=d.get("basename", "combined"),
            resolution=d.get("resolution", "1080p"),
            quality=d.get("quality", "medium"),
            frame_rate=d.get("frame_rate", "source"),
            normalize_audio=bool(d.get("normalize_audio", True)),
            produce_video=bool(d.get("produce_video", True)),
            produce_funscripts=bool(d.get("produce_funscripts", True)),
            bug=BugOverlay.from_dict(bug_dict) if bug_dict else None,
            metadata=Metadata.from_dict(d.get("metadata")),
            closing_joiner=(
                Joiner.from_dict(closing_dict) if closing_dict
                else Joiner(id="join-close", joiner_type="none")
            ),
        )


# ── Items ─────────────────────────────────────────────────────────────
@dataclass
class Segment:
    id: str
    video: str
    audio: AudioLayer = field(default_factory=AudioLayer)
    overlays: list[Overlay] = field(default_factory=list)
    funscripts_source: Literal["auto_detect", "explicit", "none"] = "auto_detect"
    funscripts_folder: Optional[str] = None
    explicit_funscripts: dict[str, str] = field(default_factory=dict)
    still_duration_s: Optional[float] = None  # required when video is a PNG
    color_temperature_k: Optional[int] = None  # 4000..10000 when set
    background: SegmentBackground = "black"  # only meaningful for stills
    bookmark: Optional[str] = None  # Phase 2
    trim_start: Optional[str] = None  # Phase 2, HH:MM:SS.mmm
    trim_end: Optional[str] = None  # Phase 2

    def is_still(self) -> bool:
        return is_still_image(self.video)

    # ── Trim accessors (Phase 2 fields, now live) ─────────────────
    def trim_start_ms(self) -> int:
        """Trim-start in ms; 0 when unset (= play from the source's start)."""
        return parse_hms_ms(self.trim_start) if self.trim_start else 0

    def trim_end_ms(self) -> Optional[int]:
        """Trim-end in ms, or None when unset (= play to the source's end)."""
        return parse_hms_ms(self.trim_end) if self.trim_end else None

    def effective_duration_ms(self, source_duration_ms: int) -> int:
        """Duration the segment actually contributes to the timeline,
        given the source video's full duration in ms.

        For untrimmed segments this is just `source_duration_ms`. For
        trimmed segments it's `(trim_end or source) - trim_start`,
        clamped to non-negative.
        """
        start = self.trim_start_ms()
        end = self.trim_end_ms()
        if end is None:
            end = source_duration_ms
        return max(0, end - start)

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "id": self.id,
            "type": "segment",
            "video": self.video,
            "audio": self.audio.to_dict(),
            "overlays": [o.to_dict() for o in self.overlays],
            "funscripts": {
                "source": self.funscripts_source,
            },
        }
        if self.funscripts_source == "explicit":
            d["funscripts"]["files"] = self.explicit_funscripts
        elif self.funscripts_source == "auto_detect" and self.funscripts_folder:
            d["funscripts"]["folder"] = self.funscripts_folder
        if self.still_duration_s is not None:
            d["still_duration_s"] = self.still_duration_s
        if self.color_temperature_k is not None:
            d["color_temperature_k"] = self.color_temperature_k
        if self.background != "black":
            d["background"] = self.background
        if self.bookmark:
            d["bookmark"] = self.bookmark
        if self.trim_start:
            d["trim_start"] = self.trim_start
        if self.trim_end:
            d["trim_end"] = self.trim_end
        return d

    @staticmethod
    def from_dict(d: dict) -> "Segment":
        fs = d.get("funscripts") or {}
        return Segment(
            id=d["id"],
            video=d["video"],
            audio=AudioLayer.from_dict(d.get("audio")),
            overlays=[Overlay.from_dict(o) for o in d.get("overlays", [])],
            funscripts_source=fs.get("source", "auto_detect"),
            funscripts_folder=fs.get("folder"),
            explicit_funscripts=fs.get("files", {}),
            still_duration_s=d.get("still_duration_s"),
            color_temperature_k=d.get("color_temperature_k"),
            background=d.get("background", "black"),
            bookmark=d.get("bookmark"),
            trim_start=d.get("trim_start"),
            trim_end=d.get("trim_end"),
        )


@dataclass
class Joiner:
    id: str
    joiner_type: JoinerType = "none"
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": "joiner",
            "joiner_type": self.joiner_type,
            "params": self.params,
        }

    @staticmethod
    def from_dict(d: dict) -> "Joiner":
        return Joiner(
            id=d["id"],
            joiner_type=d.get("joiner_type", "none"),
            params=d.get("params", {}),
        )


# ── Output channels ────────────────────────────────────────────────────
@dataclass
class OutputChannels:
    # All implemented channels default ON. Users typically want every
    # detected channel in the output; off-by-default would silently
    # drop e1/e2/prostate tracks even when they exist on the source
    # clips. Phase-2 channels stay off until they're implemented.
    main: bool = True
    multi_axis: bool = True
    three_phase_estim: bool = True
    four_phase_estim: bool = False  # Phase 2
    prostate: bool = True
    audio_estim: bool = False  # Phase 2
    pulse_frequency: bool = False  # Phase 2

    def to_dict(self) -> dict:
        return {
            "main": self.main,
            "multi_axis": self.multi_axis,
            "three_phase_estim": self.three_phase_estim,
            "four_phase_estim": self.four_phase_estim,
            "prostate": self.prostate,
            "audio_estim": self.audio_estim,
            "pulse_frequency": self.pulse_frequency,
        }

    @staticmethod
    def from_dict(d: dict | None) -> "OutputChannels":
        if not d:
            return OutputChannels()
        return OutputChannels(
            main=d.get("main", True),
            multi_axis=d.get("multi_axis", False),
            three_phase_estim=d.get("three_phase_estim", False),
            four_phase_estim=d.get("four_phase_estim", False),
            prostate=d.get("prostate", False),
            audio_estim=d.get("audio_estim", False),
            pulse_frequency=d.get("pulse_frequency", False),
        )

    def selected(self) -> list[str]:
        """Return the names of channels that are enabled."""
        return [k for k, v in self.to_dict().items() if v]


# ── Section-level overlay ─────────────────────────────────────────────
@dataclass
class SectionOverlay:
    """An image or audio file laid over a Section's timeline.

    Times are measured from the section's start (not the clip's or the
    project's), so an overlay can span clip boundaries inside a section
    without the author doing time math. Multiple overlays on one
    section stack in declaration order: first = bottom, last = top for
    images; all mixed together for audio.

    Common fields apply to both kinds:
      * file — path to the image (PNG/JPG/WEBP) or audio (mp3/wav/m4a)
      * start_s, duration_s — time window relative to the section's start
      * fade_in_s, fade_out_s — subtle transition on each end

    Image-only fields: position, opacity.
    Audio-only fields:  mix_pct (0-100; overlay's share of the mix).
    """
    id: str
    kind: SectionOverlayKind  # "image" | "audio" | "text"
    file: str  # image/audio path; unused when kind == "text"
    start_s: float = 0.0
    duration_s: float = 0.0  # 0 = play to end of section
    fade_in_s: float = 0.0
    fade_out_s: float = 0.0
    # Image/text-only: position on the frame.
    position: OverlayPosition = "center"
    # Image/text-only: opacity 0.0-1.0.
    opacity: float = 1.0
    # Image-only: render at this percentage of native size.
    scale_pct: int = 100
    # Audio-only: 0 = no overlay (clip audio dominates), 100 = overlay only.
    mix_pct: int = 50
    # Text-only fields ─────────────────────────────────────────────
    # The literal string to render. Supports "\n" for manual line
    # breaks. Ignored when kind != "text".
    text: str = ""
    # Hex colour like "#ffffff". Ignored when kind != "text".
    text_color: str = "#ffffff"
    # Point-size-ish number fed to drawtext's fontsize. Ignored when
    # kind != "text".
    font_size: int = 48
    # Filesystem-stem of the font (e.g. "Arial", "Georgia"). The UI
    # enumerates system fonts; the engine resolves this stem back to
    # a full .ttf/.otf/.ttc path at forge time. Ignored when kind !=
    # "text". Empty string means "let ffmpeg pick a default font".
    font_family: str = ""

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "file": self.file,
            "start_s": self.start_s,
            "duration_s": self.duration_s,
            "fade_in_s": self.fade_in_s,
            "fade_out_s": self.fade_out_s,
        }
        if self.kind == "image":
            d["position"] = self.position
            d["opacity"] = self.opacity
            d["scale_pct"] = self.scale_pct
        elif self.kind == "audio":
            d["mix_pct"] = self.mix_pct
        elif self.kind == "text":
            d["position"] = self.position
            d["opacity"] = self.opacity
            d["text"] = self.text
            d["text_color"] = self.text_color
            d["font_size"] = self.font_size
            d["font_family"] = self.font_family
        return d

    @staticmethod
    def from_dict(d: dict) -> "SectionOverlay":
        return SectionOverlay(
            id=d["id"],
            kind=d["kind"],
            file=d.get("file", ""),  # text overlays have no file
            start_s=float(d.get("start_s", 0.0)),
            duration_s=float(d.get("duration_s", 0.0)),
            fade_in_s=float(d.get("fade_in_s", 0.0)),
            fade_out_s=float(d.get("fade_out_s", 0.0)),
            position=d.get("position", "center"),
            opacity=float(d.get("opacity", 1.0)),
            scale_pct=int(d.get("scale_pct", 100)),
            mix_pct=int(d.get("mix_pct", 50)),
            text=d.get("text", ""),
            text_color=d.get("text_color", "#ffffff"),
            font_size=int(d.get("font_size", 48)),
            font_family=d.get("font_family", ""),
        )


# ── Section ────────────────────────────────────────────────────────────
@dataclass
class Section:
    """A group of clips joined by hard cuts.

    Sections are separated by their **leading joiner** — the transition
    that plays as this section starts (default "none" = hard cut). A
    section's own segments cut straight together inside it.
    """
    id: str
    leading_joiner: "Joiner" = field(default_factory=lambda: Joiner(
        id=new_id("join"), joiner_type="none",
    ))
    segments: list[Segment] = field(default_factory=list)
    overlays: list[SectionOverlay] = field(default_factory=list)
    name: Optional[str] = None  # override chapter title

    def chapter_name(self) -> str:
        """Return the MP4 chapter title for this section.

        Priority: explicit `name` → first segment's bookmark → first
        segment's prettified filename stem → "Section".
        """
        if self.name and self.name.strip():
            return self.name.strip()
        if self.segments:
            first = self.segments[0]
            if first.bookmark and first.bookmark.strip():
                return first.bookmark.strip()
            return prettify_filename_stem(Path(first.video).stem)
        return "Section"

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "id": self.id,
            "leading_joiner": self.leading_joiner.to_dict(),
            "segments": [s.to_dict() for s in self.segments],
        }
        if self.name:
            d["name"] = self.name
        if self.overlays:
            d["overlays"] = [o.to_dict() for o in self.overlays]
        return d

    @staticmethod
    def from_dict(d: dict) -> "Section":
        return Section(
            id=d["id"],
            leading_joiner=Joiner.from_dict(d.get("leading_joiner") or {
                "id": new_id("join"), "joiner_type": "none",
            }),
            segments=[Segment.from_dict(s) for s in d.get("segments", [])],
            overlays=[
                SectionOverlay.from_dict(o) for o in d.get("overlays", [])
            ],
            name=d.get("name"),
        )


def split_segment_at(
    segment: Segment,
    split_at_ms: int,
    new_segment_id: Optional[str] = None,
) -> tuple[Segment, Segment]:
    """Split `segment` into two at `split_at_ms` (absolute time in the
    original source video, in ms).

    The first returned segment keeps the original id and runs from the
    segment's current `trim_start_ms()` to `split_at_ms`. The second
    gets `new_segment_id` (auto-generated when None) and runs from
    `split_at_ms` to the segment's current `trim_end_ms()` (None = "to
    the end of the source").

    Raises:
        ValueError: when called on a still image, or when `split_at_ms`
            is not strictly between the segment's effective bounds.
    """
    if segment.is_still():
        raise ValueError("cannot split a still-image segment")
    start = segment.trim_start_ms()
    end = segment.trim_end_ms()  # None = open
    if split_at_ms <= start:
        raise ValueError(
            f"split_at_ms ({split_at_ms}) must be > trim_start ({start})",
        )
    if end is not None and split_at_ms >= end:
        raise ValueError(
            f"split_at_ms ({split_at_ms}) must be < trim_end ({end})",
        )

    from dataclasses import replace as _dc_replace
    head = Segment(
        id=segment.id,
        video=segment.video,
        audio=segment.audio,
        # Per-segment overlays travel with the head; cloned so that
        # later edits to the head don't reach back into whatever the
        # caller still holds. Section-level overlays are unaffected
        # (they live on Section, not Segment).
        overlays=[_dc_replace(o) for o in segment.overlays],
        funscripts_source=segment.funscripts_source,
        funscripts_folder=segment.funscripts_folder,
        explicit_funscripts=dict(segment.explicit_funscripts),
        still_duration_s=segment.still_duration_s,
        color_temperature_k=segment.color_temperature_k,
        background=segment.background,
        bookmark=segment.bookmark,
        trim_start=segment.trim_start,
        trim_end=format_hms_ms(split_at_ms),
    )
    tail = Segment(
        id=new_segment_id or new_id("seg"),
        video=segment.video,
        audio=segment.audio,
        overlays=[],
        funscripts_source=segment.funscripts_source,
        funscripts_folder=segment.funscripts_folder,
        explicit_funscripts=dict(segment.explicit_funscripts),
        still_duration_s=segment.still_duration_s,
        color_temperature_k=segment.color_temperature_k,
        background=segment.background,
        bookmark=None,  # the tail starts a new beat; let the user name it
        trim_start=format_hms_ms(split_at_ms),
        trim_end=segment.trim_end,
    )
    return head, tail


def _migrate_items_to_sections(items: list) -> list[Section]:
    """Convert a flat v1.0 `[Segment | Joiner]` list into Sections.

    Rules:
      - A non-"none" joiner starts a new section with that joiner as its
        leading joiner; any following segments belong to that section.
      - A "none" joiner is absorbed as an implicit inter-segment cut
        within the current section (since clips inside a section
        already cut straight together).
      - The first section always has a default "none" leading joiner
        unless the project opened with a non-"none" joiner.
    """
    sections: list[Section] = []
    current_segs: list[Segment] = []
    current_leading = Joiner(id=new_id("join"), joiner_type="none")
    for it in items:
        if isinstance(it, Segment):
            current_segs.append(it)
        elif isinstance(it, Joiner):
            if it.joiner_type == "none":
                continue  # inter-clip cut — absorbed
            # Flush whatever we've been building, then open a new section
            # led by this joiner.
            if current_segs or sections:
                sections.append(Section(
                    id=new_id("sec"),
                    leading_joiner=current_leading,
                    segments=current_segs,
                ))
            current_segs = []
            current_leading = it
    if current_segs or not sections:
        sections.append(Section(
            id=new_id("sec"),
            leading_joiner=current_leading,
            segments=current_segs,
        ))
    return sections


# ── Project ────────────────────────────────────────────────────────────
class Project:
    """Top-level project: list of Sections + output settings.

    Accepts either `sections=[Section, ...]` (the v2.0 canonical shape)
    or the legacy `items=[Segment | Joiner, ...]` for v1-era callers;
    the latter is auto-migrated into Sections. Passing both is an error.
    """

    def __init__(
        self,
        *,
        sections: Optional[list[Section]] = None,
        items: Optional[list] = None,
        output_channels: Optional[OutputChannels] = None,
        output: Optional[Output] = None,
        audio_beds: Optional[list[dict]] = None,
        version: str = PROJECT_VERSION,
    ) -> None:
        if sections is not None and items is not None:
            raise TypeError(
                "Project(): pass either `sections=` or `items=`, not both",
            )
        if items is not None:
            sections = _migrate_items_to_sections(items)
        self.sections: list[Section] = list(sections) if sections else []
        self.output_channels: OutputChannels = (
            output_channels if output_channels is not None else OutputChannels()
        )
        self.output: Output = output if output is not None else Output()
        self.audio_beds: list[dict] = (
            list(audio_beds) if audio_beds is not None else []
        )
        self.version: str = version

    def __repr__(self) -> str:
        return (
            f"Project(sections={len(self.sections)}, "
            f"output={self.output!r}, "
            f"output_channels={self.output_channels!r}, "
            f"version={self.version!r})"
        )

    # ── Manipulation helpers ──────────────────────────────────────
    def add_section(self, section: Section) -> None:
        self.sections.append(section)

    def remove_section(self, section_id: str) -> None:
        self.sections = [s for s in self.sections if s.id != section_id]

    def add_segment(self, segment: Segment) -> None:
        """Append a segment to the last section (create one if needed).

        Kept for compatibility with the v1 flat add-flow and for the
        common "just keep adding clips" UX. The resulting section uses
        the default "none" leading joiner.
        """
        if not self.sections:
            self.sections.append(Section(id=new_id("sec")))
        self.sections[-1].segments.append(segment)

    def add_joiner(self, joiner: Joiner) -> None:
        """Open a new section led by `joiner`; subsequent
        `add_segment` calls land in it. Kept for v1 compat."""
        self.sections.append(Section(
            id=new_id("sec"),
            leading_joiner=joiner,
            segments=[],
        ))

    def remove(self, item_id: str) -> None:
        """Remove a segment, joiner, or section by id.

        Segments: removed from whichever section owns them; empty
        sections are NOT auto-deleted (they hold the leading joiner).
        Joiners: if `item_id` matches a section's leading joiner, the
        section's leading joiner is reset to a fresh "none" cut.
        Sections: removed whole.
        """
        # Direct section match
        if any(s.id == item_id for s in self.sections):
            self.remove_section(item_id)
            return
        for sec in self.sections:
            if sec.leading_joiner.id == item_id:
                sec.leading_joiner = Joiner(
                    id=new_id("join"), joiner_type="none",
                )
                return
            sec.segments = [s for s in sec.segments if s.id != item_id]

    # ── Flattened legacy view (layout / concat code walks this) ──
    @property
    def items(self) -> list:
        """Flattened `[Joiner?, Segment, Segment, ..., Joiner?, ...]`
        view for downstream code that still walks a linear timeline.
        A section's "none" leading joiner is suppressed (it's implicit)."""
        out: list = []
        for sec in self.sections:
            if sec.leading_joiner.joiner_type != "none":
                out.append(sec.leading_joiner)
            out.extend(sec.segments)
        return out

    def segments(self) -> list[Segment]:
        return [s for sec in self.sections for s in sec.segments]

    def joiners(self) -> list[Joiner]:
        """Every non-'none' leading joiner in the project, in order."""
        return [
            sec.leading_joiner for sec in self.sections
            if sec.leading_joiner.joiner_type != "none"
        ]

    # ── Serialization ─────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "output": self.output.to_dict(),
            "output_channels": self.output_channels.to_dict(),
            "sections": [s.to_dict() for s in self.sections],
            "audio_beds": list(self.audio_beds),
        }

    @staticmethod
    def from_dict(d: dict) -> "Project":
        if "sections" in d:
            sections = [Section.from_dict(s) for s in d["sections"]]
        else:
            # v1.0 format: flat `items` list — migrate.
            legacy: list = []
            for raw in d.get("items", []):
                if raw.get("type") == "segment":
                    legacy.append(Segment.from_dict(raw))
                elif raw.get("type") == "joiner":
                    legacy.append(Joiner.from_dict(raw))
                else:
                    raise ValueError(f"Unknown item type: {raw.get('type')}")
            sections = _migrate_items_to_sections(legacy)
        return Project(
            sections=sections,
            output_channels=OutputChannels.from_dict(d.get("output_channels")),
            output=Output.from_dict(d.get("output")),
            audio_beds=list(d.get("audio_beds", [])),
            version=PROJECT_VERSION,  # always write as current
        )

    # ── Disk I/O ──────────────────────────────────────────────────
    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @staticmethod
    def load(path: str | Path) -> "Project":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return Project.from_dict(data)


# ── Validation ────────────────────────────────────────────────────────
@dataclass
class ValidationIssue:
    level: Literal["error", "warning"]
    message: str
    item_id: Optional[str] = None


def validate(project: Project) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    if not project.sections:
        issues.append(ValidationIssue("error", "Project has no sections."))
        return issues

    all_segments = project.segments()
    if not all_segments:
        issues.append(ValidationIssue("error", "Project has no segments."))

    # Every non-empty section is fine; a section may be empty only if the
    # user deliberately parked a leading joiner before populating it.
    for sec in project.sections:
        if not sec.segments:
            issues.append(ValidationIssue(
                "warning",
                f"Section {sec.id} has no segments.",
                item_id=sec.id,
            ))
        for ov in sec.overlays:
            if ov.kind not in ("image", "audio", "text"):
                issues.append(ValidationIssue(
                    "error",
                    f"Overlay {ov.id} has unknown kind '{ov.kind}'.",
                    item_id=sec.id,
                ))
            # Text overlays have no file — they carry a string instead.
            # Require non-empty text; image/audio require a real file.
            if ov.kind == "text":
                if not ov.text or not ov.text.strip():
                    issues.append(ValidationIssue(
                        "error",
                        f"Text overlay {ov.id} has no text.",
                        item_id=sec.id,
                    ))
            else:
                if not ov.file:
                    issues.append(ValidationIssue(
                        "error",
                        f"Overlay {ov.id} has no file.",
                        item_id=sec.id,
                    ))
                elif not Path(ov.file).exists():
                    issues.append(ValidationIssue(
                        "warning",
                        f"Overlay file not found: {ov.file}",
                        item_id=sec.id,
                    ))
            if ov.start_s < 0:
                issues.append(ValidationIssue(
                    "error",
                    f"Overlay {ov.id} start_s must be non-negative.",
                    item_id=sec.id,
                ))
            if ov.duration_s < 0:
                issues.append(ValidationIssue(
                    "error",
                    f"Overlay {ov.id} duration_s must be non-negative "
                    "(use 0 for 'play to end of section').",
                    item_id=sec.id,
                ))
            if ov.fade_in_s < 0 or ov.fade_out_s < 0:
                issues.append(ValidationIssue(
                    "error",
                    f"Overlay {ov.id} fade durations must be non-negative.",
                    item_id=sec.id,
                ))
            if ov.kind == "image":
                if ov.position not in OVERLAY_POSITIONS:
                    issues.append(ValidationIssue(
                        "error",
                        f"Overlay {ov.id} position '{ov.position}' is not "
                        f"one of {', '.join(OVERLAY_POSITIONS)}.",
                        item_id=sec.id,
                    ))
                if not (0.0 <= ov.opacity <= 1.0):
                    issues.append(ValidationIssue(
                        "error",
                        f"Overlay {ov.id} opacity must be between 0.0 and 1.0.",
                        item_id=sec.id,
                    ))
                if not (1 <= ov.scale_pct <= 400):
                    issues.append(ValidationIssue(
                        "error",
                        f"Overlay {ov.id} scale_pct must be between "
                        "1 and 400.",
                        item_id=sec.id,
                    ))
            elif ov.kind == "audio":
                if not (0 <= ov.mix_pct <= 100):
                    issues.append(ValidationIssue(
                        "error",
                        f"Overlay {ov.id} mix_pct must be between 0 and 100.",
                        item_id=sec.id,
                    ))

    # Freeze the flat timeline once so `previous_last_frame` lookups below
    # don't rebuild the list on every segment.
    flat_items = project.items

    # File existence for segments
    for seg in project.segments():
        if not Path(seg.video).exists():
            issues.append(ValidationIssue(
                "error",
                f"Video file not found: {seg.video}",
                item_id=seg.id,
            ))
        if seg.audio.mode == "replace":
            if not seg.audio.file:
                issues.append(ValidationIssue(
                    "error",
                    "audio.mode=replace requires audio.file",
                    item_id=seg.id,
                ))
            elif not Path(seg.audio.file).exists():
                issues.append(ValidationIssue(
                    "error",
                    f"Replacement audio file not found: {seg.audio.file}",
                    item_id=seg.id,
                ))
        for ov in seg.overlays:
            if ov.type == "image" and ov.file and not Path(ov.file).exists():
                issues.append(ValidationIssue(
                    "warning",
                    f"Overlay image not found: {ov.file}",
                    item_id=seg.id,
                ))
            if ov.type == "text" and not ov.content:
                issues.append(ValidationIssue(
                    "warning",
                    "Text overlay with empty content will render nothing.",
                    item_id=seg.id,
                ))

        # Still image / duration coupling
        if seg.is_still():
            if seg.still_duration_s is None:
                issues.append(ValidationIssue(
                    "error",
                    "Segment video is a still image; still_duration_s is required.",
                    item_id=seg.id,
                ))
            elif seg.still_duration_s <= 0:
                issues.append(ValidationIssue(
                    "error",
                    "still_duration_s must be positive.",
                    item_id=seg.id,
                ))
        elif seg.still_duration_s is not None:
            issues.append(ValidationIssue(
                "warning",
                "still_duration_s is set but the video is not a still image; it will be ignored.",
                item_id=seg.id,
            ))

        # Color temperature bounds
        if seg.color_temperature_k is not None:
            if not (4000 <= seg.color_temperature_k <= 10000):
                issues.append(ValidationIssue(
                    "error",
                    "color_temperature_k must be between 4000 and 10000.",
                    item_id=seg.id,
                ))

        # Trim bounds. Don't probe for source duration here — that's a
        # forge-time check (too expensive at validation). Just make sure
        # the strings parse and trim_start < trim_end when both are set,
        # and stills can't be trimmed (their duration is set elsewhere).
        if seg.trim_start or seg.trim_end:
            if seg.is_still():
                issues.append(ValidationIssue(
                    "error",
                    "Still-image segments cannot be trimmed; use "
                    "still_duration_s instead.",
                    item_id=seg.id,
                ))
            try:
                start_ms = seg.trim_start_ms()
            except ValueError as exc:
                issues.append(ValidationIssue(
                    "error",
                    f"Invalid trim_start: {exc}",
                    item_id=seg.id,
                ))
                start_ms = None
            try:
                end_ms = seg.trim_end_ms()
            except ValueError as exc:
                issues.append(ValidationIssue(
                    "error",
                    f"Invalid trim_end: {exc}",
                    item_id=seg.id,
                ))
                end_ms = None
            if (
                start_ms is not None
                and end_ms is not None
                and start_ms >= end_ms
            ):
                issues.append(ValidationIssue(
                    "error",
                    f"trim_start ({seg.trim_start}) must be less than "
                    f"trim_end ({seg.trim_end}).",
                    item_id=seg.id,
                ))

        # Background = previous_last_frame rules
        if seg.background == "previous_last_frame":
            if not seg.is_still():
                issues.append(ValidationIssue(
                    "error",
                    "background=previous_last_frame is only supported for "
                    "still-image segments (PNG).",
                    item_id=seg.id,
                ))
            # Must have a preceding Segment in the flat timeline order
            seg_index = next(
                (i for i, it in enumerate(flat_items) if it is seg), -1,
            )
            prev_segment_exists = any(
                isinstance(it, Segment) for it in flat_items[:seg_index]
            )
            if not prev_segment_exists:
                issues.append(ValidationIssue(
                    "error",
                    "background=previous_last_frame requires a preceding "
                    "segment in the project.",
                    item_id=seg.id,
                ))

    # Joiner params
    for j in project.joiners():
        if j.joiner_type == "fade_to_black":
            d = j.params.get("duration_s")
            f = j.params.get("fade_s")
            # With fade/hold decoupled, duration_s (hold) = 0 is a
            # valid pure-crossfade configuration as long as fade_s > 0.
            # Reject only when both are zero or either is negative.
            if d is None and f is None:
                issues.append(ValidationIssue(
                    "warning",
                    "fade_to_black joiner has no duration_s/fade_s; "
                    "defaulting to hold=5.0, fade=1.0.",
                    item_id=j.id,
                ))
            else:
                d_val = 0.0 if d is None else float(d)
                f_val = 0.0 if f is None else float(f)
                if d_val < 0:
                    issues.append(ValidationIssue(
                        "error",
                        "fade_to_black duration_s (hold) must be >= 0.",
                        item_id=j.id,
                    ))
                if f_val < 0:
                    issues.append(ValidationIssue(
                        "error",
                        "fade_to_black fade_s must be >= 0.",
                        item_id=j.id,
                    ))
                if d_val == 0 and f_val == 0:
                    issues.append(ValidationIssue(
                        "error",
                        "fade_to_black needs duration_s (hold) > 0 or "
                        "fade_s > 0 — otherwise the joiner is a no-op.",
                        item_id=j.id,
                    ))

    # Output settings
    out = project.output
    if not out.folder:
        issues.append(ValidationIssue(
            "warning",
            "output.folder is not set; CLI forge will require --output.",
        ))
    if out.resolution not in RESOLUTION_KEYS:
        issues.append(ValidationIssue(
            "error",
            f"output.resolution '{out.resolution}' is not one of "
            f"{', '.join(RESOLUTION_KEYS)}.",
        ))
    if out.quality not in QUALITY_CRF:
        issues.append(ValidationIssue(
            "error",
            f"output.quality '{out.quality}' is not one of "
            f"{', '.join(QUALITY_CRF.keys())}.",
        ))
    if out.frame_rate not in FRAME_RATE_KEYS:
        issues.append(ValidationIssue(
            "error",
            f"output.frame_rate '{out.frame_rate}' is not one of "
            f"{', '.join(FRAME_RATE_KEYS)}.",
        ))
    if not out.produce_video and not out.produce_funscripts:
        issues.append(ValidationIssue(
            "error",
            "At least one of produce_video / produce_funscripts must be true.",
        ))
    if out.bug is not None:
        bug = out.bug
        if not Path(bug.file).exists():
            issues.append(ValidationIssue(
                "warning",
                f"Bug overlay file not found: {bug.file}",
            ))
        if bug.corner not in ("tl", "tr", "bl", "br"):
            issues.append(ValidationIssue(
                "error",
                f"bug.corner '{bug.corner}' must be one of tl, tr, bl, br.",
            ))
        if not (0.0 <= bug.opacity <= 1.0):
            issues.append(ValidationIssue(
                "error",
                "bug.opacity must be between 0.0 and 1.0.",
            ))
        if bug.margin_px < 0:
            issues.append(ValidationIssue(
                "error",
                "bug.margin_px must be non-negative.",
            ))

    return issues


def new_id(prefix: str = "item") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"
