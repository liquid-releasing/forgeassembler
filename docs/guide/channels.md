# Output Channels

**Every funscript channel your clips carry is forged.** You don't opt in.
ForgeAssembler takes the union of what the clips actually have and writes one
combined file per channel.

## One folder per device

A current FunscriptForge scene ships around forty funscripts across nine
**stations** — one per device it can drive. Three of those stations (E-Stim,
FOC-Stim and FOC-Stim 4-phase) write channels with the *same names* —
`alpha`, `beta`, `volume`, `frequency`, `pulse_frequency`, `pulse_rise_time`
and the prostate set — clamped differently for each piece of hardware. So a
channel name alone no longer names a file, and the output cannot be flat.

A forge therefore writes the universal stroke script at the top level and
gives every station its own folder, using the same folder names a
FunscriptForge export uses:

```text
combined.mp4
combined.funscript                      # universal stroke, most players
combined.heatmap.png
E-Stim/combined.alpha.funscript
E-Stim/combined.beta.funscript
FOC-Stim/combined.alpha.funscript       # same channel, different clamping
FOC-Stim 4-phase/combined.e1.funscript
MultiFunPlayer/combined.funscript       # TCode's own L0
MultiFunPlayer/combined.surge.funscript
Handy/combined.handy.funscript
Bass Shaker/combined.shaker.funscript
```

Point restim at the folder for the device you actually own; point
MultiFunPlayer at `MultiFunPlayer/`. A heatmap sits beside each funscript.

A funscript that arrives with no station — a loose `<stem>.alpha.funscript`
sitting next to a video, where nothing on disk says which device it was
clamped for — is filed under the station that owns that channel, and it feeds
every station's copy of it. Two clips, one from a `.forge` scene and one a
plain video, still join into one continuous track.

## Channel groups

Some channels fall into named groups:

| Group | Channels | Used by |
|---|---|---|
| Main | `main` | Standard linear devices (Handy, Kiiroo, etc.) |
| Multi-axis | `pitch`, `roll`, `surge`, `sway`, `twist` | SR6 / OSR2 and similar 6DOF rigs |
| 3-phase estim | `alpha`, `beta` | restim 3-phase rigs |
| 4-phase estim | `e1`, `e2`, `e3`, `e4` | FOC-Stim 4-phase (per-electrode power) |
| Prostate | `alpha-prostate`, `beta-prostate`, `volume-prostate` | restim prostate variants |
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
with a **gaps** badge, and the Inspector's Funscripts tab names exactly which
channels are missing — so you can see it before you forge rather than during
playback.

### A gap is a difference, not a fault

The badge compares each scene against the **other scenes in this
compilation**. It does not mean anything is broken, and most gaps need no
action at all.

When a scene was created in FunscriptForge, its author chose which devices and
stations to generate for. Two scenes made months apart, or made for different
devices, legitimately carry different channel sets — and every one of those
differences shows up here as a gap.

What matters is **which** channel is missing:

| The gap | What it usually means | Worth acting on? |
| ------- | --------------------- | ---------------- |
| A multi-axis channel (`surge`, `sway`, `roll`, `pitch`, `twist`) | The scene was generated with a different multi-axis style. Those axes were never meant to exist for it. | Rarely. The axes present still play. |
| A whole device you use — the FOC-Stim set, say | That scene will be **silent on that device** for its whole length while the others drive it. | Yes. This is the one that spoils a session. |
| A parameter channel (`pulse_rise_time`, `frequency`) | The scene predates that parameter, or its station did not emit it. | Sometimes — the device falls back to its own default. |

So read the badge as *"this scene is the odd one out, here is how"* rather than
as an error. A compilation where every scene is missing the same thing has no
gaps at all, and is perfectly fine.

### Closing a gap

ForgeAssembler does not generate channels — it joins what exists. To fill a
real gap, open that scene in FunscriptForge and generate the station you want,
then re-export it. Two things worth knowing first:

- If the channel already exists in the scene's project but not in its `.forge`,
  the bundle is simply **older than the project**. Re-exporting is enough; no
  regeneration needed.
- If it does not exist in the project either, it has to be generated, and that
  is an authoring decision — the multi-axis style, the stations — not something
  that can be filled in mechanically.

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

In the **Produce** panel of the **Output** tab:

- **Video (MP4)** — on by default
- **Funscripts** — on by default
- **Audio (haptic estim)** — on by default

Each toggle is independent. You can turn off Video to render only
the funscript bundle (faster — no ffmpeg encoding). You can turn off
Funscripts and Audio to render only the long video. At least one of
the three must be on.

## The `.forge` scene

A forge also writes `<basename>.forge` — the same bundle format
FunscriptForge exports, carrying:

- `motion.funscript` and every station's channels, at their station paths
- the joined haptic audio, under `audio/`
- **this compilation's** chapters: one per section, the same boundaries the
  MP4's markers and every funscript carry
- the **joined analysis** — beats and the audio waveform, shifted onto the
  compilation's timeline from the scenes that supplied them. This is what
  lets a two-hour compilation open with a waveform immediately instead of
  being decoded first
- a hero frame and one thumbnail per chapter
- a `manifest.ffmeta` that says it was made by ForgeAssembler and lists which
  scenes went into it

This is the file that keeps a compilation inside the forge family: **reopen it
in FunscriptForge** to keep editing, or **play it in ForgePlayer** as one
scene. Without it a compilation is only an MP4 and a pile of funscripts.

The bundle does **not** carry the combined video by default — a compilation is
measured in gigabytes. The manifest records the video's name, size and a hash
of its first megabyte, which is how a consumer finds it again on disk. Turn on
*…with the video inside it* in **Produce** when you want one self-contained
file to hand to someone who does not have the footage.

Turn the whole thing off with the **.forge scene** switch, or `--no-forge-bundle`
on the CLI.

## Heatmaps

Every funscript written gets a companion `.heatmap.png` beside it, in the
same folder — `combined.heatmap.png` at the top, `E-Stim/combined.alpha.heatmap.png`
next to that station's alpha, and so on. They come with the **funscripts**,
not the video, so a funscripts-only forge still produces them.

Each is a density map of that channel across the whole combined output — a
quick read of pacing: dense stretches, quiet stretches, spikes, and the blank
regions where a clip didn't carry the channel.

---

Next: **[Resolution & scaling](resolution.md)** — what the output
resolution setting does to your footage, and what it cannot do.
