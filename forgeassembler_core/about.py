# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""About metadata for ForgeAssembler.

Single source of truth for version, credits, and license content shown in:
  - the app's About panel
  - `cli.py --version`
"""

from __future__ import annotations

__all__ = [
    "APP_NAME",
    "ABOUT_MARKDOWN",
    "TAGLINE",
    "VERSION",
    "about_title",
    "about_text",
]

VERSION = "0.0.1"
APP_NAME = "ForgeAssembler"
TAGLINE = "Assemble many short haptic clips into one long video."


ABOUT_MARKDOWN = f"""
### {APP_NAME} {VERSION}

{TAGLINE}

Build a long haptic video from many short ones. Edit each clip in
FunscriptForge, then assemble them here with your choice of transitions
and per-segment overlays. Outputs a combined video + every channel's
combined funscripts + a `.forge` scene, with chapter markers at every
section boundary.

---

#### Open source credits

- **[FFmpeg](https://ffmpeg.org)** — video and audio processing. LGPL 2.1+ / GPL 2+.
- **[Tauri](https://tauri.app)** — native desktop shell. MIT / Apache 2.0.
- **[React](https://react.dev)** — user interface library. MIT.
- **[Lucide](https://lucide.dev)** — icon set. ISC.

Full third-party license text is bundled with the release under `LICENSES/`.

#### AI assistance

Written by human and Claude AI (Anthropic).

---

#### Community

Questions, bug reports, and feedback welcome in
[our Discord](https://discord.gg/Eytatcx8Jm).

---

#### License

**{APP_NAME}(TM)** is a trademark of Liquid Releasing.

(c) 2026 [Liquid Releasing](https://github.com/liquid-releasing).
Licensed under the [MIT License](https://github.com/liquid-releasing/forgeassembler/blob/main/LICENSE).
"""


def about_title() -> str:
    return f"{APP_NAME} {VERSION}"


def about_text() -> str:
    return (
        f"{APP_NAME} {VERSION}\n"
        f"{TAGLINE}\n\n"
        "Open source credits:\n"
        "  - FFmpeg (LGPL/GPL)\n"
        "  - Tauri (MIT / Apache 2.0)\n"
        "  - React (MIT)\n"
        "  - Lucide (ISC)\n\n"
        "Written by human and Claude AI (Anthropic).\n\n"
        "Community: discord.gg/Eytatcx8Jm\n\n"
        f"{APP_NAME} is a trademark of Liquid Releasing.\n"
        "(c) 2026 Liquid Releasing. MIT License."
    )
