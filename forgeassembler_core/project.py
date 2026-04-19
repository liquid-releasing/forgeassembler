# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Project data model + JSON load/save/validate."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

PROJECT_VERSION = "1.0"

AudioMode = Literal["keep", "replace", "silence"]
JoinerType = Literal["none", "fade_to_black"]
OverlayType = Literal["image", "text"]
BugCorner = Literal["tl", "tr", "bl", "br"]

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
class Output:
    """Project-level output configuration (resolution, audio, toggles, bug)."""
    folder: Optional[str] = None
    basename: str = "combined"
    resolution: str = "1080p"
    normalize_audio: bool = True
    produce_video: bool = True
    produce_funscripts: bool = True
    bug: Optional[BugOverlay] = None

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "folder": self.folder,
            "basename": self.basename,
            "resolution": self.resolution,
            "normalize_audio": self.normalize_audio,
            "produce_video": self.produce_video,
            "produce_funscripts": self.produce_funscripts,
        }
        if self.bug is not None:
            d["bug"] = self.bug.to_dict()
        return d

    @staticmethod
    def from_dict(d: dict | None) -> "Output":
        if not d:
            return Output()
        bug_dict = d.get("bug")
        return Output(
            folder=d.get("folder"),
            basename=d.get("basename", "combined"),
            resolution=d.get("resolution", "1080p"),
            normalize_audio=bool(d.get("normalize_audio", True)),
            produce_video=bool(d.get("produce_video", True)),
            produce_funscripts=bool(d.get("produce_funscripts", True)),
            bug=BugOverlay.from_dict(bug_dict) if bug_dict else None,
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
    bookmark: Optional[str] = None  # Phase 2
    trim_start: Optional[str] = None  # Phase 2, HH:MM:SS.mmm
    trim_end: Optional[str] = None  # Phase 2

    def is_still(self) -> bool:
        return is_still_image(self.video)

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
    main: bool = True
    multi_axis: bool = False
    three_phase_estim: bool = False
    four_phase_estim: bool = False  # Phase 2
    prostate: bool = False
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


# ── Project ────────────────────────────────────────────────────────────
@dataclass
class Project:
    items: list[Segment | Joiner] = field(default_factory=list)
    output_channels: OutputChannels = field(default_factory=OutputChannels)
    output: Output = field(default_factory=Output)
    audio_beds: list[dict] = field(default_factory=list)  # Phase 2
    version: str = PROJECT_VERSION

    # ── Manipulation helpers ──────────────────────────────────────
    def add_segment(self, segment: Segment) -> None:
        self.items.append(segment)

    def add_joiner(self, joiner: Joiner) -> None:
        self.items.append(joiner)

    def remove(self, item_id: str) -> None:
        self.items = [i for i in self.items if i.id != item_id]

    def segments(self) -> list[Segment]:
        return [i for i in self.items if isinstance(i, Segment)]

    def joiners(self) -> list[Joiner]:
        return [i for i in self.items if isinstance(i, Joiner)]

    # ── Serialization ─────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "output": self.output.to_dict(),
            "output_channels": self.output_channels.to_dict(),
            "items": [i.to_dict() for i in self.items],
            "audio_beds": list(self.audio_beds),
        }

    @staticmethod
    def from_dict(d: dict) -> "Project":
        items: list[Segment | Joiner] = []
        for raw in d.get("items", []):
            if raw.get("type") == "segment":
                items.append(Segment.from_dict(raw))
            elif raw.get("type") == "joiner":
                items.append(Joiner.from_dict(raw))
            else:
                raise ValueError(f"Unknown item type: {raw.get('type')}")
        return Project(
            items=items,
            output_channels=OutputChannels.from_dict(d.get("output_channels")),
            output=Output.from_dict(d.get("output")),
            audio_beds=list(d.get("audio_beds", [])),
            version=d.get("version", PROJECT_VERSION),
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

    if not project.items:
        issues.append(ValidationIssue("error", "Project has no items."))
        return issues

    if not any(isinstance(i, Segment) for i in project.items):
        issues.append(ValidationIssue("error", "Project has no segments."))

    # Joiners must sit between two segments
    last_kind = None
    for item in project.items:
        kind = "segment" if isinstance(item, Segment) else "joiner"
        if kind == "joiner" and last_kind != "segment":
            issues.append(ValidationIssue(
                "error",
                "Joiner must follow a segment.",
                item_id=item.id,
            ))
        last_kind = kind
    if last_kind == "joiner":
        issues.append(ValidationIssue("error", "Project cannot end with a joiner."))

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

    # Joiner params
    for j in project.joiners():
        if j.joiner_type == "fade_to_black":
            d = j.params.get("duration_s")
            if d is None:
                issues.append(ValidationIssue(
                    "warning",
                    "fade_to_black joiner has no duration_s; defaulting to 1.0.",
                    item_id=j.id,
                ))
            elif d <= 0:
                issues.append(ValidationIssue(
                    "error",
                    "fade_to_black duration_s must be positive.",
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
