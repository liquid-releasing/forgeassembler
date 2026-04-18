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
3. **Select output channels.** At the top of the left panel, tick which
   funscript variants the combined output should contain.
4. **Forge.** One button. ForgeAssembler concatenates the videos,
   concatenates every selected funscript channel in lockstep, writes
   chapter markers at every segment boundary, and saves the project as
   reusable JSON.

## Three tabs

### Tab 1 — Build

The main surface. Add segments and joiners, review the project list,
see the live heatmap + beatmap preview of the combined result above the
Forge button.

### Tab 2 — Joiners

The joiner library. Browse available joiner types with descriptions,
adjust the defaults that new joiners start with.

- v1: None, FadeToBlack
- Phase 2: TitleCard (built from the template DSL), plus any templates
  you author in Tab 3

### Tab 3 — Templates (Phase 2)

A YAML editor for defining custom joiner templates. Describe a joiner
as a composition of primitives (background source, text layers, image
overlays, audio, composite modes) and ForgeAssembler applies it
anywhere you drop that joiner in a project. The tier where the
creative work happens without drag-and-drop.

## Segments are rich

A segment is "a paragraph in the final video" — it has:

- **Video layer** — the base clip. Can be a regular video file or a
  still image (for title cards built on a frozen frame).
- **Audio layer** — keep the original video audio, replace it with an
  external file (voiceover, music bed), or go silent.
- **Overlay layers** — image overlays (logos, lower-thirds) and text
  overlays (titles, captions), each with position, size, fade-in /
  fade-out timing, and opacity.
- **Funscript layers** — when the segment has a funscript (or a full
  FunscriptForge output bundle), all selected channels flow through to
  the combined output.

Segments without funscripts are allowed — intro/outro/title segments
are pure video+audio.

## Joiners are transitions

Joiners sit **between** segments and describe how one ends and the
next begins.

- **None** — straight cut. The most common transition.
- **FadeToBlack** — previous segment fades out over N seconds (video +
  audio), holds black for an optional interval, next segment fades in
  over N seconds. During the joiner, the funscript holds the last
  position of the previous segment.

## Output channels

One project-level control determines which funscript variants end up
in the combined bundle:

- **2D main** — the primary `.funscript`.
- **Multi-axis** — pitch, roll, surge, sway, twist.
- **3-phase estim** — alpha + beta (Tingler, EstimHero, ZC95).
- **4-phase estim** — extra channels for 4-phase rigs *(Phase 2)*.
- **Prostate channels** — alpha-prostate, beta-prostate.
- **Audio estim** — stereostim.wav, legacy.wav *(Phase 2)*.
- **Pulse frequency** — pulse_frequency.funscript *(Phase 2)*.

If a channel is selected but missing from some segments, ForgeAssembler
asks whether to drop the channel from the output or abort.

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
- **Codec/resolution/FPS mismatch** — warning; ffmpeg re-encodes to
  bridge. A future phase adds an explicit normalize pre-pass.

## What it doesn't do

- Not a video editor. No cut-within-clip, no color grading, no effects
  beyond transitions and overlays. For that, use DaVinci Resolve or
  Premiere.
- Not a funscript editor. For per-clip authoring, use FunscriptForge.
- Not a transcoder. We pass video through ffmpeg but we don't offer
  output-format pickers or quality sliders.
- No audio mastering. Levels are your responsibility upstream.
