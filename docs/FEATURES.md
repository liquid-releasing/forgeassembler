# ForgeAssembler — Features

User-facing feature summary. For the data model and processing pipeline,
see [ARCHITECTURE.md](ARCHITECTURE.md).

## The core workflow

1. **Add segments.** Point at a folder — ForgeAssembler detects the
   video and all its associated funscripts (main, multi-axis, 3-phase
   estim channels, prostate channels, audio estim WAVs, pulse-frequency).
   Or point at a single file.
2. **Choose joiners.** Between any two segments, pick how they should
   connect: *None* (straight cut) or *FadeToBlack* with a configurable
   duration.
3. **Configure the project.** In the sidebar, pick the output resolution,
   select which funscript channels to include, toggle audio loudness
   normalization, and optionally attach a corner **bug** (a PNG logo
   that rides every segment).
4. **Forge.** One button. ForgeAssembler concatenates the videos,
   concatenates every selected funscript channel in lockstep, writes
   chapter markers at every segment boundary, and saves the project as
   reusable JSON.

## Two tabs

### Tab 1 — Build

The main surface. Add segments and joiners, review the project list,
adjust per-segment options (including color temperature with a preview
frame), and see the live heatmap + beatmap preview of the combined
result above the Forge button.

### Tab 2 — Joiners

The joiner library. Browse available joiner types with descriptions,
adjust the defaults that new joiners start with.

- v1: None, FadeToBlack
- Phase 2: extra joiner types (e.g. crossfade, dissolve)

## Segments are rich

A segment is "a paragraph in the final video" — it has:

- **Video layer** — the base clip. Can be a regular video file or a
  **still image** (PNG) for title cards, brand slates, and framed
  captions. Stills are held for a user-specified duration.
- **Audio layer** — keep the original video audio, replace it with an
  external file (voiceover, music bed), or go silent.
- **Overlay layers** — image overlays (logos, lower-thirds, lower-third
  captions) with position, size, fade-in / fade-out timing, and opacity.
  Design your overlays in your preferred tool (Figma, Canva, Affinity)
  and supply them as PNGs — ForgeAssembler doesn't do typography, so
  there's no font management, no template DSL, no text layout engine.
- **Color temperature** *(optional, per segment)* — nudge a single
  segment warmer or cooler (4000K–10000K) to better match its
  neighbours. A "preview frame" button renders one frame with the
  current setting so you're not adjusting blind. No global
  auto-color-match — that's a colorist's job and is deliberately out
  of scope.
- **Funscript layers** — when the segment has a funscript (or a full
  FunscriptForge output bundle), all selected channels flow through to
  the combined output.

Segments without funscripts are allowed — intro/outro/title segments
are pure video+audio.

### Title cards via PNG

Rather than generating title text ourselves, ForgeAssembler treats a
title card as *a segment whose video layer is a PNG*. You design the
card in any image tool (logo, typography, gradients, whatever you
want), save as PNG, add it as a segment with a duration and an
optional audio file, and it concats into the final output like any
other segment. That includes the intro "steel pour" title card, the
Chapter-2 name plate, and the outro branded slate in the canonical
FunscriptForge demo video.

## Joiners are transitions

Joiners sit **between** segments and describe how one ends and the
next begins.

- **None** — straight cut. The most common transition.
- **FadeToBlack** — previous segment fades out over N seconds (video +
  audio), holds black for an optional interval, next segment fades in
  over N seconds. During the joiner, the funscript holds the last
  position of the previous segment.

## Output settings

Project-level controls in the sidebar:

- **Produce** — two checkboxes controlling what ForgeAssembler writes
  on forge. Both default **on**; at least one must be on.
  - **Video (MP4)** — when off, skip the ffmpeg video pipeline entirely.
    Fast path for "I already cut the video in DaVinci, I just need the
    combined haptic bundle."
  - **Funscripts** — when off, skip funscript concat and the heatmap
    previews. The **Output channels** section below becomes disabled
    (greyed out) to make the cascade obvious. Fast path for "I only
    care about the video assembly, not the haptic channels."
  - **Chapter markers are always written** when video is produced,
    regardless of whether funscripts are produced. They're cheap
    metadata and genuinely useful in any player.
- **Output resolution** — the canonical size every segment is scaled to
  before concatenation. Choose from:
  - **16:9 widescreen:** `1080p` (1920×1080), `1440p` (2560×1440), `4K` (3840×2160)
  - **21:9 ultrawide / cinematic:** `UltraWide 1080p` (2560×1080), `UltraWide 1440p` (3440×1440)
  - **4:3 standard:** `4:3 HD` (1440×1080)
  - **Vertical / portrait:** `3:4 Vertical HD` (1080×1440), `9:16 Vertical HD` (1080×1920)
  - **Source** — copy the resolution of the first segment
  
  Default is `1080p`. Aspect ratio is preserved — narrower segments get
  pillarbox (bars on the sides), taller segments get letterbox (bars on
  the top and bottom). A future phase adds a crop-to-fill option.
- **Normalize audio loudness** — toggle. When on, the combined audio
  is processed through ffmpeg's `loudnorm` filter targeting −16 LUFS
  (the YouTube reference level), so uneven per-segment levels even out
  without you having to hand-mix. Single-pass; applied to the final
  audio, not per segment.
- **Bug** *(optional)* — a PNG (with transparency) that ForgeAssembler
  overlays in a corner of every segment. Pick the PNG, the corner
  (`top-left`, `top-right`, `bottom-left`, `bottom-right`), an opacity
  (0–100%), and a margin in pixels. Classic "network logo in the
  corner" branding, in one project-level control. Per-segment override
  to hide the bug on specific segments is a Phase 2 feature.

## Output channels

One project-level control determines which funscript variants end up
in the combined bundle:

- **2D main** — the primary `.funscript`.
- **Multi-axis** — pitch, roll, surge, sway, twist.
- **3-phase estim** — alpha + beta (Tingler, EstimHero, ZC95).
- **4-phase estim** — extra channels for 4-phase rigs *(Phase 2)*.
- **Prostate channels** — alpha-prostate, beta-prostate.
- **Pulse frequency** — pulse_frequency.funscript *(Phase 2)*.

If a channel is selected but missing from some segments, ForgeAssembler
asks whether to drop the channel from the output or abort.

## Haptic-estim audio

A separate top-level **Produce → Audio (haptic estim)** toggle (default
on) tells the engine to concatenate per-channel haptic-estim audio
files (`.stereostim.wav`, `.legacy.wav`, `.prostate.stereostim.wav`)
in lockstep with the video. One combined WAV per channel is written
alongside the funscripts: `<basename>.stereostim.wav`,
`<basename>.legacy.wav`, `<basename>.prostate.stereostim.wav`.

Segments without an audio file for a given channel get silence-fill
at 48 kHz stereo so the combined output stays lockstep. Channels with
no audio in any segment are skipped. Per-segment trim windows propagate
to the audio inputs (same `-ss` / `-t` semantics as the video pipeline).

## Project files

Every forge writes a `.forgeproject.json` alongside the output. Users
can reload it (iterate quickly), hand-edit it (reorder items, tweak
joiners, change output paths), or generate it from a Python script
(batch automation).

## Live preview

As items are added to the project list, the main area above the Forge
button shows a **heatmap** and **beatmap** of the combined funscript so
far, plus running duration, action count, and per-channel stats. No
rendering required; previews are generated in-process.

## Chapter markers

Every segment boundary gets a chapter marker in the output MP4 (playable
in any modern video player) and in the output funscript (consumed by
FunscriptForge and haptic players that respect chapter metadata).

## CLI + automation

The same binary ships a CLI for scripting:

```
forgeassembler forge project.json       # run a saved project
forgeassembler detect folder/           # preview what auto-detects
forgeassembler validate project.json    # check project without forging
forgeassembler list-joiners
```

Pair it with a Python script that generates project JSON by walking
folder trees and the whole long-form-video assembly is automatable.
Version-control your project.json alongside source clips, and your
"recipe" is reproducible forever.

## Error handling

- **Missing funscript variant** — prompt: drop the variant from output
  or abort.
- **Corrupt video** — prompt: skip this segment or abort.
- **Codec/resolution/FPS mismatch** — resolved automatically by scaling
  every segment to the project's output resolution.

## What it doesn't do

- Not a video editor. No cut-within-clip, no effects beyond transitions,
  overlays, and the per-segment temperature nudge. For grading, compositing,
  or per-clip editing, use DaVinci Resolve or Premiere.
- **No cross-clip color matching.** The per-segment temperature slider
  lets you nudge a single clip warmer or cooler; it does not try to
  make 10 clips shot on 10 cameras look like one camera. That's a
  colorist's job.
- Not a funscript editor. For per-clip authoring, use FunscriptForge.
- Not a transcoder. We pass video through ffmpeg but we don't offer
  output-format pickers or quality sliders.
- No audio mastering beyond the project-level loudness normalize
  toggle. Per-segment EQ, compression, and ducking are upstream
  concerns.
