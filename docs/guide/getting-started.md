# Getting Started

This page gets ForgeAssembler running and walks you through your first
combined output. Plan about ten minutes end-to-end.

## What you need

- A Windows, macOS, or Linux machine (x86-64)
- 8 GB RAM minimum
- A few FunscriptForge-style clip folders: each contains an `.mp4`
  plus one or more `.funscript` files (optionally with
  `estim/`, `multi_axis/`, `prostate/` sub-folders for channel
  funscripts)

ForgeAssembler does not need ffmpeg installed — the release bundles
its own.

---

## 1. Install

### Option A — Release bundle (recommended)

1. Download the latest release for your OS from
   [forgeassembler-releases](https://github.com/liquid-releasing/forgeassembler-releases/releases).
2. Unzip into a folder of your choice.
3. Launch `ForgeAssembler.exe` (Windows), `ForgeAssembler.app` (macOS),
   or `./ForgeAssembler` (Linux).

On first launch a small native window opens showing the ForgeAssembler
UI. The app runs entirely on your machine — nothing is uploaded.

### Option B — Run from source

```bash
git clone https://github.com/liquid-releasing/forgeassembler.git
cd forgeassembler
pip install -r requirements.txt -r requirements-desktop.txt
python forgeassembler.py
```

---

## 2. Your first forge

Once the window is open, you'll see two main areas:

- **Sidebar (left)** — output settings: resolution, channels,
  audio normalization, metadata
- **Build tab (centre)** — the project you're assembling: sections,
  clips, overlays, joiners

### Add your first clip

1. In the **Add Clips** panel at the bottom, either:
   - Click **📄 File Browse** → pick an `.mp4`, OR
   - Paste a full path (or a folder path) into the text input
2. Choose the **ONE NEW section** radio option.
3. Click **Add**.

A new section card appears with your clip, its duration, and any
detected funscripts (`Funscripts: main, multi_axis, ...`).

### Add a second clip

Repeat step 1, but this time choose **Into LAST section** to
cut-join the new clip into the existing section. Or pick **NEW ONE
section** to start a fresh section with its own chapter marker.

### Forge

1. Pick an output folder (default: next to your project) by clicking
   **Forge**.
2. Wait. The status line shows progress; forging a one-minute output
   takes roughly thirty seconds on a laptop.

When it finishes you'll have:

- `<project>.mp4` — the combined video
- `<project>.main.funscript`, `<project>.multi_axis.funscript`, etc.
  — concatenated channel funscripts
- `<project>.heatmap.png` — a heat map of the main funscript track
- `<project>.json` — reloadable project file (save it somewhere)

---

## Next steps

- **[Sections & segments](sections-and-segments.md)** — the core
  mental model you'll use for every project
- **[Overlays](overlays.md)** — drop images, audio, and text on top
  of any section
- **[Joiners](joiners.md)** — fade-to-black between sections and at
  the very end
- **[Channels](channels.md)** — pick which funscript channels get
  written
- **[Debug mode](debug-mode.md)** — capture a clean bug report when
  something goes wrong
