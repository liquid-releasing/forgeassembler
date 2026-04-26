# Output Channels

Funscripts come in flavours. Each flavour is a separate file with
its own name suffix:

| Channel | Suffix | Used by |
|---|---|---|
| Main | `.funscript` | Standard linear devices (Handy, Kiiroo, etc.) |
| Multi-axis | `.pitch.funscript`, `.roll.funscript`, `.surge.funscript`, `.sway.funscript`, `.twist.funscript` | SR6 / OSR2 and similar 6DOF rigs |
| 3-phase estim | `.alpha.funscript`, `.beta.funscript` | restim 3-phase rigs |
| Prostate | `.alpha-prostate.funscript`, `.beta-prostate.funscript` | restim prostate variants |
| 4-phase estim *(Phase 2)* | `.e1.funscript`, `.e2.funscript`, `.e3.funscript` | restim 4-phase rigs — concat not yet wired |

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

The sidebar also shows **four_phase_estim** and **pulse_frequency**.
These are off by default because the concat logic isn't written yet.
Safe to ignore until a future release lands them.

## Haptic-estim audio (per-channel WAVs)

Some haptic toolchains generate audio files alongside the funscripts —
restim, for example, can render `.stereostim.wav`, `.legacy.wav`, and
`.prostate.stereostim.wav` from a funscript and a device profile.
ForgeAssembler concatenates these in lockstep with the video.

When **Audio (haptic estim)** is on in the Produce panel, the engine:

1. Walks each segment looking for `.stereostim.wav` / `.legacy.wav` /
   `.prostate.stereostim.wav` siblings (immediate folder, plus the
   same channel sub-folders that funscript detection scans).
2. For each channel that any segment carries, concatenates the
   per-segment audio into one combined output WAV named
   `<basename>.stereostim.wav`, `<basename>.legacy.wav`, etc.
3. Segments missing a channel get silence-filled at 48 kHz stereo so
   the combined WAV stays lockstep with the video. This means a
   project with one segment that has a `stereostim.wav` and three
   that don't still produces a valid 48 kHz stereo
   `<basename>.stereostim.wav` with silence in the gaps.
4. Channels with no audio in any segment are skipped (no useless
   100%-silent files).

Per-segment trim windows (Split clip at time…) propagate to the
audio inputs the same way they do to video — `-ss <trim_start>` and
`-t <effective_duration>`.

## Produce video / funscripts / audio without the others

In the **Produce** panel of the sidebar:

- **Video (MP4)** — on by default
- **Funscripts** — on by default
- **Audio (haptic estim)** — on by default

Each toggle is independent. You can turn off Video to render only
the funscript bundle (faster — no ffmpeg encoding). You can turn off
Funscripts and Audio to render only the long video. At least one of
the three must be on.

## Heatmap

When **Produce video** is on, ForgeAssembler also writes a
`.heatmap.png` alongside the output. It's a visual density map of
the main funscript track across the whole combined output. Handy
for a quick read of pacing — dense stretches, quiet stretches,
spikes.

---

Next: **[Debug mode](debug-mode.md)** — what to turn on when
something goes wrong, and how to capture a clean bug report.
