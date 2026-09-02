# Output Channels

**Every funscript channel your clips carry is forged.** You don't opt in.
ForgeAssembler takes the union of what the clips actually have and writes one
combined file per channel, named the way FunscriptForge names them —
`<basename>.funscript` for main, `<basename>.<channel>.funscript` for the rest.

A finished FunscriptForge scene commonly ships around twenty channels. Some
fall into named groups:

| Group | Channels | Used by |
|---|---|---|
| Main | `main` | Standard linear devices (Handy, Kiiroo, etc.) |
| Multi-axis | `pitch`, `roll`, `surge`, `sway`, `twist` | SR6 / OSR2 and similar 6DOF rigs |
| 3-phase estim | `alpha`, `beta` | restim 3-phase rigs |
| Prostate | `alpha-prostate`, `beta-prostate` | restim prostate variants |
| Pulse frequency | `pulse_frequency` | restim pulse control |

The rest are **device and parameter tracks** — `handy`, `lovense`, `ossm`,
`vacuglide`, `shaker`, `volume`, `volume-prostate`, `frequency`,
`pulse_rise_time`, and anything else a future FunscriptForge release invents.
They have no group of their own and need none: concatenating `volume` is the
same operation as concatenating `alpha`, so they ride through automatically.

The **Output channels** card on the Output tab shows what was found, grouped,
with per-channel coverage. Its switches are **vetoes** — they subtract a whole
group from the output. There is nothing to turn *on*, because detection has
already decided what exists.

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

## Gaps

Clips in one compilation rarely carry identical channel sets. Where a clip
lacks a channel its neighbours have, that stretch of the combined script is
**left blank** — no actions, so a device holds its last position. The channels
that *are* present stay in lockstep with the video.

Nothing is synthesised to fill a gap. The Build tab flags the affected clips
with a **gaps** badge naming exactly which channels they're missing, so you can
see it before you forge rather than during playback.

## Haptic-estim audio (per-channel WAVs)

Some haptic toolchains generate audio files alongside the funscripts —
restim, for example, can render `.stereostim.wav`, `.legacy.wav`, and
`.prostate.stereostim.wav` from a funscript and a device profile.
ForgeAssembler concatenates these in lockstep with the video.

Recent FunscriptForge bundles carry **MP3s** (`stim`, `stim-prostate`, `beat`),
which come out as `<basename>.mp3`, `<basename>.prostate.mp3` and
`<basename>.beat.mp3`. Older loose-file layouts use WAVs
(`.stereostim.wav`, `.legacy.wav`, `.prostate.stereostim.wav`) and keep those
names. The channel key carries its own extension, so whatever went in comes
back out under the same suffix.

When **Audio (haptic estim)** is on in the Produce panel, the engine:

1. Collects each segment's haptic audio — from the `.forge` bundle it was
   imported from, or from siblings beside the video (immediate folder plus the
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

**By design, the engine emits every estim channel any segment carries
— stereostim, legacy, and prostate — regardless of whether your
current device needs them.** The downstream player (ForgePlayer, or
whatever your setup uses) selects the right channel at playback time
based on the user's hardware profile. Forge time produces all
artifacts; playback time consumes only what's relevant. This keeps
forged outputs portable across devices without re-rendering.

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

## Heatmaps

Every funscript written gets a companion `.heatmap.png` beside it —
`<basename>.heatmap.png` for main, `<basename>.alpha.heatmap.png` for alpha, and
so on. They come with the **funscripts**, not the video, so a
funscripts-only forge still produces them.

Each is a density map of that channel across the whole combined output — a
quick read of pacing: dense stretches, quiet stretches, spikes, and the blank
regions where a clip didn't carry the channel.

---

Next: **[Debug mode](debug-mode.md)** — what to turn on when
something goes wrong, and how to capture a clean bug report.
