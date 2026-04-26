# ForgeAssembler — Architecture

This document captures the data model, processing pipeline, and design
decisions behind ForgeAssembler. It is the source of truth for engineers
and Claude agents working on the code. User-facing product docs live in
[FEATURES.md](FEATURES.md).

## Positioning in the Liquid Releasing family

| Tool | Role |
|---|---|
| **FunscriptForge** | Shape and polish a *single* raw funscript into a finished, device-safe script with transforms, multi-axis channels, estim channels, and audio WAVs. |
| **ForgeYT** | Download one YouTube audio file onto disk, no account or cloud. |
| **ForgeAssembler** | Concatenate many finished FunscriptForge outputs into a single long video + funscript bundle. Not an editor — a linear assembler. |

FunscriptForge handles per-clip artistry. ForgeAssembler handles sequencing,
transitions, and delivery of the combined long-form output. Most users of
ForgeAssembler are also users of FunscriptForge.

## Core vocabulary

- **Segment** — a top-level item in the project list. Roughly "a paragraph
  in the final video". Has layers running in parallel:
  video, audio, image overlays. The video layer may be a clip or a
  still PNG (title cards are just segments whose video is a PNG).
- **Layer** — a track within a segment: video, audio, image overlay.
  Each layer has optional start/end and fade timings.
- **Joiner** — a transition between two segments. V1 types: `none` (hard
  cut), `fade_to_black` (duration configurable). Phase 2 adds richer
  joiner types (crossfade, dissolve, etc.) as additional subclasses —
  **not** via a template DSL.
- **Title card** — *not a distinct type*. It's a segment whose `video`
  is a PNG, rendered for a configured duration. No text rendering in
  ForgeAssembler itself; user supplies the designed image.
- **Bug** — a project-level PNG overlaid in a corner of every segment
  (opacity + margin configurable). Classic "network logo in the
  corner" branding.
- **Output resolution** — the canonical size every segment is scaled to
  before concat. Values (stored as the JSON key string):
  - 16:9: `1080p` (1920×1080), `1440p` (2560×1440), `4k` (3840×2160)
  - 21:9: `uw_1080p` (2560×1080), `uw_1440p` (3440×1440)
  - 4:3: `4_3_hd` (1440×1080)
  - 3:4 / 9:16 portrait: `3_4_hd` (1080×1440), `9_16_hd` (1080×1920)
  - `source` — copy the first segment's resolution
  
  In v1 the scale mode is always **pad** (letterbox/pillarbox). A
  `source` value delays resolution until ffprobe of the first segment
  at forge time. A Phase 2 `crop` fill mode will add `output.fill_mode`
  to the schema.
- **Normalize audio** — project-level toggle that applies ffmpeg's
  `loudnorm` filter (−16 LUFS) to the final audio track.
- **Color temperature** — optional per-segment override in Kelvin
  (4000–10000). Implemented via ffmpeg's `colortemperature` filter. A
  "generate preview frame" action renders one frame with the current
  value so the user can tune visually.
- **Audio bed** — a project-level audio track that spans time across
  segments. Reserved in the v1 schema (`"audio_beds": []`), implemented
  in Phase 2. For MVP, users pre-split bed audio into per-segment files.
- **Output channels** — the set of funscript variants included in the
  combined output (main, multi-axis, 3-phase estim, prostate, audio
  estim, pulse frequency). User-selected at project level.
- **Bookmark** — per-segment text that becomes a chapter marker in the
  combined video and in the combined funscript (Phase 2).
- **Trim range** — per-segment start/end times in `HH:MM:SS.mmm` format
  that slice the incoming media before concatenation (Phase 2).

## Project file format

ForgeAssembler projects are JSON. Users can hand-edit them and reload.

```json
{
  "version": "1.0",
  "output": {
    "folder": "C:/out/",
    "basename": "combined",
    "resolution": "1080p",
    "normalize_audio": true,
    "produce_video": true,
    "produce_funscripts": true,
    "produce_audio_estim": true,
    "bug": {
      "file": "C:/demo/branding/lr_bug.png",
      "corner": "bottom-right",
      "margin_px": 24,
      "opacity": 0.85
    }
  },
  "output_channels": {
    "main": true,
    "multi_axis": false,
    "three_phase_estim": false,
    "four_phase_estim": false,
    "prostate": false,
    "pulse_frequency": false
  },
  "items": [
    {
      "id": "seg-1",
      "type": "segment",
      "video": "C:/demo/intro/steel_pour.mp4",
      "audio": {
        "mode": "replace",
        "file": "C:/demo/intro/beat_part_1.mp3"
      },
      "overlays": [
        {
          "type": "image",
          "file": "C:/demo/intro/lr_logo.png",
          "position": "center",
          "start_s": 0.5,
          "end_s": 3.0,
          "fade_in_s": 0.5,
          "fade_out_s": 0.5,
          "opacity": 1.0
        }
      ],
      "funscripts": {
        "source": "auto_detect",
        "folder": null
      }
    },
    {
      "id": "join-1-2",
      "type": "joiner",
      "joiner_type": "none",
      "params": {}
    },
    {
      "id": "seg-2",
      "type": "segment",
      "video": "C:/demo/title2/victoria_oats_wild_ride.png",
      "still_duration_s": 4.5,
      "audio": {
        "mode": "replace",
        "file": "C:/demo/intro/beat_part_2.mp3"
      }
    },
    {
      "id": "join-2-3",
      "type": "joiner",
      "joiner_type": "fade_to_black",
      "params": {"duration_s": 2.0}
    },
    {
      "id": "seg-3",
      "type": "segment",
      "video": "C:/demo/main/demo.mp4",
      "audio": {"mode": "replace", "file": "C:/demo/main/voiceover.mp3"},
      "color_temperature_k": 6200,
      "funscripts": {"source": "auto_detect"}
    }
  ],
  "audio_beds": []
}
```

Notes:

- Every item has an `id`. IDs are stable so Phase 2 can reference
  segments from another item.
- `output.resolution` is one of `1080p`, `1440p`, `4k`, `uw_1080p`,
  `uw_1440p`, `4_3_hd`, `3_4_hd`, `9_16_hd`, or `source`. Defaults to
  `1080p`. See the vocabulary list above for pixel dimensions.
- `output.normalize_audio` is a boolean. When true, the combined audio
  runs through ffmpeg `loudnorm` targeting −16 LUFS (single-pass).
- `output.produce_video`, `output.produce_funscripts`, and
  `output.produce_audio_estim` are booleans (default all `true`).
  **At least one must be true** — validator rejects all-false. Each
  pipeline runs independently: turning `produce_video` off skips the
  ffmpeg video pipeline entirely; `produce_funscripts` off skips
  funscript concat + heatmap; `produce_audio_estim` off skips the
  per-channel haptic-WAV concat. Chapter markers are written whenever
  `produce_video` is true.
- `output.bug` is optional. When present, the PNG is composited into
  every segment's video layer at the specified corner/margin/opacity.
  Per-segment override (e.g. hide bug on the outro) is Phase 2.
- `output_channels` is a project-level dictionary of booleans. Missing
  channel files in any segment trigger a prompt at forge time.
- `audio_beds` is reserved; v1 ignores it.
- Segments may have `funscripts` omitted entirely — those are pure
  video/audio segments (intro, title cards, outro) with no haptic track.
- A segment whose `video` points at a PNG (extension check) is a
  **title card**: looped for `still_duration_s` seconds. No typography
  is rendered by ForgeAssembler; the PNG is authored externally.
- `color_temperature_k` is optional per-segment (4000–10000 Kelvin).
  When set, applies ffmpeg `colortemperature` filter to that segment.
- `overlays[].type` is `image` in v1. Text overlays are deferred to a
  future phase that bundles an open-licensed font; until then, bake
  text into PNG overlays upstream.

## Processing pipeline

At forge time:

1. **Validate project JSON** against schema (including: at least one
   of `output.produce_video` / `output.produce_funscripts` /
   `output.produce_audio_estim` must be true). Hard errors abort;
   warnings surface in the UI.
2. **Resolve each segment**: locate the video file, auto-detect
   associated funscripts in the segment's folder (main, multi-axis,
   estim channels). Probe duration via ffprobe. Funscript resolution
   is skipped when `produce_funscripts` is false.
3. **Build layout**: compute the running start time of each segment and
   joiner. Joiners insert a gap of known duration between segments.
4. **Concatenate videos** *(skipped when `output.produce_video` is false)*:
   emit an ffmpeg `filter_complex` graph that
   (a) normalizes every segment's video to the project's canonical
   `output.resolution` via `scale` + `pad` + `setsar=1`, (b) applies
   the per-segment `colortemperature` filter if set, (c) composites
   image overlays for each segment, (d) inserts joiner transitions
   (e.g. `xfade` for fade-to-black), (e) overlays the project-level
   `bug` PNG onto every segment via `overlay`, and (f) concats
   everything to a single mp4.
5. **Concatenate audio** *(skipped when `output.produce_video` is false)*:
   per segment, select original / replaced / silence. Concat in
   lockstep with video. If `output.normalize_audio` is true, run the
   final audio track through `loudnorm=I=-16:TP=-1.5:LRA=11`.
   Phase 2 mixes audio beds on top.
6. **Concatenate funscripts** *(skipped when `output.produce_funscripts`
   is false)*: for each selected output channel, load each segment's
   funscript for that channel, shift all `at` timestamps by the
   segment's running start, and concat. Actions that fall in joiner
   gaps are dropped (v1: hold last position; Phase 2: synthesize via
   a FunscriptForge transform).
7. **Concatenate haptic-estim audio** *(skipped when
   `output.produce_audio_estim` is false)*: for each estim audio
   channel any segment carries (`stereostim.wav`, `legacy.wav`,
   `prostate.stereostim.wav`), build an ffmpeg filter graph that
   concatenates the per-segment audio with `-ss`/`-t` honoring trim
   windows. Segments missing a channel get `anullsrc` of the matching
   duration; channels missing in every segment are skipped (no
   100%-silent files). Output is PCM 16-bit at 48 kHz stereo named
   `<basename>.<channel>.wav`.
8. **Write chapter markers**: one chapter per segment. Always written
   to the MP4 when video is produced (via ffmpeg `-metadata` chapters)
   and to each output funscript's `chapters` array when funscripts are
   produced. Chapter markers cost nothing and help every player.
9. **Write project JSON** alongside output for reproducibility.
10. **Generate heatmap + beatmap preview** PNGs per channel *(skipped
    when `output.produce_funscripts` is false)*.

## ffmpeg filter-complex approach

Every segment is normalized to the project's canonical resolution
(`scale` + `pad` to preserve aspect ratio) before anything else:

```text
[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,
     pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1[v0]
```

Still images (title cards) are loaded with `-loop 1 -t N` so they
produce a fixed-duration video stream that feeds the same pipeline.

Optional per-segment color temperature:

```text
[v0]colortemperature=temperature=6200[v0_warm]
```

Segments then concatenate with the `concat` filter (not the demuxer,
because we need re-encoding anyway to honour the size + temperature +
bug pipeline):

```text
[v0][0:a][v1][1:a]concat=n=2:v=1:a=1[vraw][aout]
```

For a fade-to-black joiner we use `xfade`:

```text
[v0][v1]xfade=transition=fadeblack:duration=2:offset=X[vout]
```

For per-segment image overlays, we pre-apply before concat:

```text
[v0][1:v]overlay=x=(W-w)/2:y=(H-h)/2:enable='between(t,0.5,3)'[v0_with_logo]
```

**Bug overlay** (project-level, applied to every segment):

```text
[vraw][bug]overlay=x=W-w-24:y=H-h-24:format=auto[vbug]
```

The bug PNG is read with `-loop 1` and its opacity is applied via a
pre-stage `format=rgba,colorchannelmixer=aa=0.85`.

**Audio loudness normalize** (project-level, applied to the final
concatenated audio track):

```text
[aout]loudnorm=I=-16:TP=-1.5:LRA=11[afinal]
```

Text rendering (`drawtext`) is **not** used in v1 — users author
title cards and captions as PNGs upstream. When text returns in a
later phase, it will ship with a bundled open-licensed font.

Codec/FPS mismatches: by construction we re-encode everything (the
bug + temperature + resolution normalize pipeline requires it), so
input codec/FPS mismatches are handled transparently.

## Funscript concatenation

Funscripts are simple JSON:

```json
{
  "actions": [{"at": 0, "pos": 0}, {"at": 100, "pos": 50}, ...],
  "chapters": [...]
}
```

Concatenation is timestamp shifting:

```python
def concat_funscripts(parts: list[tuple[Funscript, float]]) -> Funscript:
    out_actions = []
    offset_ms = 0
    for fs, duration_ms in parts:
        for a in fs["actions"]:
            out_actions.append({"at": a["at"] + offset_ms, "pos": a["pos"]})
        offset_ms += duration_ms
    return {"actions": out_actions}
```

Multi-axis and estim variants concat the same way, once per selected
channel. Joiner gaps in v1 have no actions inserted — the device holds
the last position from the previous segment until the next segment
begins.

## Codebase layout

```text
forgeassembler/
├── forgeassembler.py              # PyWebView launcher (dual-mode)
├── ui.py                           # Streamlit UI, two tabs
├── cli.py                          # argparse CLI entry point
├── forgeassembler_core/
│   ├── __init__.py
│   ├── about.py                    # version + credits
│   ├── project.py                  # Project model, load/save JSON, validate
│   ├── detect.py                   # folder → video + funscripts
│   ├── layout.py                   # compute running timeline
│   ├── filters.py                  # per-segment filter-chain builders
│   │                               #   (scale/pad, colortemperature, overlays)
│   ├── concat_video.py             # ffmpeg filter_complex orchestration
│   │                               #   (incl. bug, loudnorm, xfade)
│   ├── concat_funscript.py         # funscript timestamp shift + concat
│   ├── joiners/
│   │   ├── __init__.py
│   │   ├── base.py                 # Joiner ABC
│   │   ├── none_joiner.py          # straight cut
│   │   └── fade_to_black.py        # fade/hold/fade
│   ├── preview.py                  # single-frame preview rendering
│   │                               #   (for color-temp tuning)
│   ├── chapters.py                 # mp4 chapter markers
│   ├── heatmap.py                  # funscript heatmap + beatmap previews
│   └── forge.py                    # top-level forge() orchestrator
├── tests/                          # pytest
│   ├── fixtures/                   # tiny test videos + funscripts
│   ├── test_project.py
│   ├── test_detect.py
│   ├── test_layout.py
│   ├── test_concat_funscript.py
│   ├── test_filters.py             # filter-chain string builders
│   ├── test_concat_video.py        # integration, slow
│   └── test_cli.py
├── .streamlit/config.toml
├── media/                          # icons, wordmark, LR logo
├── ForgeAssembler.spec             # PyInstaller
├── requirements.txt
├── requirements-desktop.txt
├── requirements-dev.txt            # pytest, ruff
├── .github/workflows/release.yml
├── README.md
├── LICENSE (MIT)
├── THIRD_PARTY_LICENSES.md
└── .gitignore
```

## CLI

`forgeassembler` ships with a CLI for automation and scripted batch
assembly. Same process entry point; Streamlit launcher only fires when
called with no CLI args.

```text
forgeassembler forge <project.json>            # run a saved project
forgeassembler forge <project.json> --no-video          # funscripts only
forgeassembler forge <project.json> --no-funscripts     # video only
forgeassembler detect <folder>                 # preview what auto-detects
forgeassembler validate <project.json>         # schema + resolvability check
forgeassembler list-joiners                    # show joiner types and params
forgeassembler --version
```

`--no-video` / `--no-funscripts` override the corresponding
`output.produce_*` booleans in the project JSON for the duration of
that run. Passing both is a usage error.

Exit codes: 0 success, 1 validation error, 2 resolution error (file
missing), 3 ffmpeg error.

A Python script can generate project JSON from scanning a folder tree
and pipe into `forgeassembler forge`, which is the primary automation
story we're selling.

## Testing strategy

- **Pure-logic unit tests** (`test_project.py`, `test_detect.py`,
  `test_layout.py`, `test_concat_funscript.py`): no ffmpeg, no real
  files beyond tiny fixtures. Fast, run on every commit.
- **Integration tests** (`test_concat_video.py`): use 1-second fixture
  videos and ffmpeg to validate end-to-end forging. Marked slow; may
  run only on tag pushes in CI.
- **CLI tests** (`test_cli.py`): subprocess the CLI entry point, assert
  exit codes and file outputs.
- **No UI tests in v1.** The Streamlit UI is thin over the core and
  exercised by hand + CLI coverage.

## Phase map

### Phase 1 (v0.0.1-alpha)

- Two tabs: Build, Joiners
- Segments with video (clip or PNG still) + audio options + image overlays
- Title cards = segments whose `video` is a PNG with `still_duration_s`
- Joiners: None, FadeToBlack
- Output resolution dropdown (16:9 1080p/1440p/4K, 21:9 ultrawide
  1080p/1440p, 4:3 HD, 3:4 vertical HD, 9:16 vertical HD, source).
  Always scale-and-pad in v1.
- Produce-what toggles (`produce_video`, `produce_funscripts`,
  `produce_audio_estim` — at least one must be true). Enables
  "funscripts-only", "video-only", and "haptic-WAVs-only" fast paths.
- Audio loudness normalize toggle (ffmpeg `loudnorm`, −16 LUFS)
- Project-level bug overlay (PNG in a chosen corner)
- Per-segment color temperature (4000–10000 K) with preview-frame button
- Output channels: main, multi-axis, 3-phase estim
- Project JSON save/load
- Chapter markers (mp4 + funscript)
- Heatmap + beatmap preview
- Summary stats in sidebar
- Error handling: missing variant prompt, corrupt video skip
- CLI: `forge`, `detect`, `validate`, `list-joiners`
- Tests: unit + CLI + 1-2 integration fixtures

### Phase 2

- **Timeline tab** — thumbnail strip per segment with joiner markers,
  click-to-play source clip
- `output.fill_mode` — `pad` (v1 default) vs `crop` (new). Crop scales
  to cover the output frame and trims excess on the short axis.
- Per-segment bug override (hide/replace bug on specific segments)
- Per-segment trim ranges (HH:MM:SS.mmm)
- Per-segment bookmark text
- Audio estim WAV concat (resample to common rate)
- Pulse frequency + 4-phase estim
- Transform-based funscript fill during joiner gaps
- Additional joiner types (crossfade, dissolve, etc.) as Joiner subclasses
- Project-level audio beds
- Reorder UI in the list panel

### Phase 3+

- Text overlays with a bundled open-licensed font
- Video-on-video overlays (PIP)
- "Last frame of segment N" as an importable still source
- Batch mode from the UI (drop a folder of project.json files)
- Per-clip color-match assistance (reference clip + auto-align)
