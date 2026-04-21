# Output Channels

Funscripts come in flavours. Each flavour is a separate file with
its own name suffix:

| Channel | Suffix | Used by |
|---|---|---|
| Main | `.funscript` | Standard linear devices (Handy, Kiiroo, etc.) |
| Multi-axis | `.multi_axis.funscript` | SR6 / OSR2 and similar 6DOF rigs |
| 3-phase estim | `.e1.funscript`, `.e2.funscript`, `.e3.funscript` | RESTIM, 3-channel estim |
| Prostate | `.prostate.funscript` | Prostate-specific devices |

The sidebar **Output channels** section lets you pick which channels
get written for the combined output.

## How detection works

When you add a clip, ForgeAssembler looks for matching funscript
files in:

1. The same folder as the clip (`your_clip.mp4` →
   `your_clip.funscript`, `your_clip.multi_axis.funscript`, …)
2. Named sub-folders: `estim/`, `multi_axis/`, `prostate/`,
   `audio_estim/` — matching the FunscriptForge output layout

Root-level matches win over sub-folder dupes if the same name appears
in both places.

Detected channels show up on each segment card as
`Funscripts: main, multi_axis, e1, e2, e3, prostate, …`.

## How concatenation works

For each enabled channel, ForgeAssembler walks every segment in
playback order and stitches the funscript timelines back-to-back.
Gaps (fade-to-black bridges) produce silent stretches in the
funscript.

If a specific clip is missing a channel you've enabled, the engine
leaves that gap silent rather than failing — so a project with one
clip that doesn't have multi-axis still produces a valid
`<project>.multi_axis.funscript` with gaps for the missing stretch.

## Default channels

By default ForgeAssembler writes **main**, **multi_axis**,
**three_phase_estim**, and **prostate**. Turn channels off in the
sidebar if you want fewer files.

## Phase-2 channels (not yet implemented)

The sidebar also shows **four_phase_estim**, **audio_estim**, and
**pulse_frequency**. These are off by default and greyed out because
the concat logic isn't written yet. Safe to ignore until a future
release lands them.

## Produce funscripts without producing a video

In the **Output** section of the sidebar, toggle:

- **Produce video** — on by default
- **Produce funscripts** — on by default

You can turn off **Produce video** if you only need the combined
funscript bundle (faster, no ffmpeg encoding). Useful when
iterating on funscript edits without re-rendering a long video.

## Heatmap

When **Produce video** is on, ForgeAssembler also writes a
`.heatmap.png` alongside the output. It's a visual density map of
the main funscript track across the whole combined output. Handy
for a quick read of pacing — dense stretches, quiet stretches,
spikes.

---

Next: **[Debug mode](debug-mode.md)** — what to turn on when
something goes wrong, and how to capture a clean bug report.
