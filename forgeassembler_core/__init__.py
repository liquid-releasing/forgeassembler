"""ForgeAssembler core — framework-agnostic data model, detection, and concat."""

from .about import (
    ABOUT_MARKDOWN,
    APP_NAME,
    TAGLINE,
    VERSION,
    about_title,
)
from .concat_funscript import (
    FunscriptPart,
    concat_funscripts,
    read_funscript,
    write_funscript,
)
from .detect import (
    DetectedClip,
    categorize_channels,
    detect_file,
    detect_folder,
)
from .joiners import REGISTRY as JOINER_REGISTRY
from .joiners import Joiner, JoinerSpec, all_specs as joiner_specs, instantiate as instantiate_joiner
from .project import (
    RESOLUTION_KEYS,
    RESOLUTION_PIXELS,
    AudioLayer,
    BugOverlay,
    Joiner as ProjectJoiner,  # alias to avoid clash with joiners.Joiner
    Output,
    OutputChannels,
    Overlay,
    Project,
    PROJECT_VERSION,
    Segment,
    ValidationIssue,
    is_still_image,
    new_id,
    validate,
)

__all__ = [
    "ABOUT_MARKDOWN",
    "APP_NAME",
    "AudioLayer",
    "BugOverlay",
    "DetectedClip",
    "FunscriptPart",
    "JOINER_REGISTRY",
    "Joiner",
    "JoinerSpec",
    "Output",
    "OutputChannels",
    "Overlay",
    "PROJECT_VERSION",
    "Project",
    "ProjectJoiner",
    "RESOLUTION_KEYS",
    "RESOLUTION_PIXELS",
    "Segment",
    "TAGLINE",
    "VERSION",
    "ValidationIssue",
    "about_title",
    "categorize_channels",
    "concat_funscripts",
    "detect_file",
    "detect_folder",
    "instantiate_joiner",
    "is_still_image",
    "joiner_specs",
    "new_id",
    "read_funscript",
    "validate",
    "write_funscript",
]
