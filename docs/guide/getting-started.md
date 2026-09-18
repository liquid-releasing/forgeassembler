# Getting Started

This page gets ForgeAssembler running and walks you through your first
combined output. Plan about ten minutes end-to-end.

## What you need

- A Windows, macOS, or Linux machine (x86-64)
- 8 GB RAM minimum
- Something to assemble. Either:
    - **`.forge` scenes** exported from FunscriptForge — the preferred
      input, because one file carries the video reference, every
      funscript channel, the estim audio, and the analysis sidecars, OR
    - **clip folders**: an `.mp4` plus one or more sibling
      `.funscript` files

ForgeAssembler does not need ffmpeg installed — the release bundles
its own.

---

## 1. Install

### Option A — Release bundle (recommended)

1. Download the latest release for your OS from
   [forgeassembler-releases](https://github.com/liquid-releasing/forgeassembler-releases/releases).
2. Run the installer (Windows `.msi`, macOS `.dmg`) and launch
   **ForgeAssembler**.

The app runs entirely on your machine — nothing is uploaded.

### Option B — Run from source

You need Python 3.11+, Node 20+, and a Rust toolchain.

```bash
git clone https://github.com/liquid-releasing/forgeassembler.git
cd forgeassembler
pip install -r requirements.txt

cd ui/web
npm install
npm run tauri:dev
```

---

## 2. Your first forge

The app opens on the **Home** screen: **New compilation**, **Open
project…**, and your recent projects. Click **New compilation**.

You land in a three-step pipeline across the top — **Build**,
**Output**, **Forge**. Each step has an Accept button in the footer;
accepting chains you to the next step.

### Add your scenes

In the **Build** tab header:

- **Add .forge scene…** — pick one `.forge` file.
- **Add folder…** — pick a folder of them, added in one go.

**Each `.forge` scene becomes its own section**, and a section boundary
is a chapter marker in the finished video. So a compilation of five
scenes gives you five chapters without any extra work.

If the bundle does not carry its video — the default export is lean, and
references the video beside it — you are asked to point at the file once.

A section card shows its clips, each with duration, the channels it
carries as device pills (Stroke / Multi-axis / E-Stim), and a **gaps**
pill if this clip lacks a channel its neighbours have. That pill is
worth reading: a channel missing from one clip goes quiet for that
stretch of the finished compilation.

### Add a plain video to a section

**Add clip** in a section header takes a video (plus any funscripts
sitting beside it). A video is a clip *within* a section, not a section
of its own — so use this when two pieces of footage belong to the same
chapter.

### Set a transition

The **+** between two clips adds a transition there, splitting the
section at that point and opening the joiner picker. Pick **None** for a
straight cut or **Fade through black** for a fade — any colour, with
independent fade-out, hold, and fade-in. Crossfade and swipe are listed
but marked *soon*; no engine implements them yet.

### Trim a clip

Click a clip to open the **Inspector**. Its **Source** tab has the
player, with the whole scene drawn on a strip above it — the motion
track, the audio waveform, and a ruler. Click anywhere on the strip to
jump there, park the playhead, then **Set in** / **Set out**. The
regions you are cutting are shaded on the strip as you go.

### Check the join

The preview band along the bottom of the Build tab draws the **joined
funscript** — the actual concatenated result, computed by the same code
the forge uses, so it cannot drift from what you get.

### Output and forge

**Accept and chain** moves you to **Output**: resolution, encode
quality, frame rate, audio normalization, and which funscript channels
to write. The defaults are fine for a first run.

Accept again to reach **Forge**, and press it. Progress streams into the
footer. A one-minute output takes roughly thirty seconds on a laptop;
GPU encoding is used automatically when your machine has it (see
[GPU acceleration](gpu-acceleration.md)).

Use **Save as…** to choose where the output lands and what it is called
— that name is the basename for everything written:

- `<name>.mp4` — the combined video, with chapter markers at every
  section boundary
- `<name>.funscript` — the universal stroke script, plus **one folder per
  device** (`E-Stim/`, `FOC-Stim/`, `MultiFunPlayer/`, …) holding that
  station's channels. Three stations write channels with the same names, so
  they cannot share a flat folder — see [channels](channels.md)
- `<name>.forge` — **the compilation as a scene**: every channel, the joined
  analysis, and its chapters in one file. Reopen it in FunscriptForge to keep
  editing, or play it in ForgePlayer
- `<name>.heatmap.png` — a heat map beside each funscript
- `<name>.forgeproject.json` — the reloadable project

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
- **[Resolution & scaling](resolution.md)** — what choosing 4K does,
  and what it does not do
- **[CLI](cli.md)** — everything the app does, scriptable
