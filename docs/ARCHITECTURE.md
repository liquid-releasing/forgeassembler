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
  video, audio, overlays (image, text).
- **Layer** — a track within a segment: video, audio, image overlay, text
  overlay. Each layer has optional start/end and fade timings.
- **Joiner** — a transition between two segments. V1 types: `none` (hard
  cut), `fade_to_black` (duration configurable). Phase 2 adds richer
  joiners via a declarative template DSL.
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
    "basename": "combined"
  },
  "output_channels": {
    "main": true,
    "multi_axis": false,
    "three_phase_estim": false,
    "four_phase_estim": false,
    "prostate": false,
    "audio_estim": false,
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
      "video": "C:/demo/title2/frozen_last_frame.png",
      "audio": {
        "mode": "replace",
        "file": "C:/demo/intro/beat_part_2.mp3"
      },
      "overlays": [
        {
          "type": "text",
          "content": "Victoria Oats Wild Ride",
          "font": "Bebas Neue",
          "size": 120,
          "color": "#ffffff",
          "outline_color": "#000000",
          "outline_width": 2,
          "position": "center",
          "start_s": 0.3,
          "end_s": 4.5,
          "fade_in_s": 0.3,
          "fade_out_s": 0.3
        }
      ]
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
      "funscripts": {"source": "auto_detect"}
    }
  ],
  "audio_beds": []
}
```

Notes:

- Every item has an `id`. IDs are stable so Phase 2 can reference "last
  frame of seg-1" from another item.
- `output_channels` is a project-level dictionary of booleans. Missing
  channel files in any segment trigger a prompt at forge time.
- `audio_beds` is reserved; v1 ignores it.
- Segments may have `funscripts` omitted entirely — those are pure
  video/audio segments (intro, title cards, outro) with no haptic track.

## Processing pipeline

At forge time:

1. **Validate project JSON** against schema. Hard errors abort; warnings
   surface in the UI.
2. **Resolve each segment**: locate the video file, auto-detect
   associated funscripts in the segment's folder (main, multi-axis,
   estim channels). Probe duration via ffprobe.
3. **Build layout**: compute the running start time of each segment and
   joiner. Joiners insert a gap of known duration between segments.
4. **Concatenate videos**: emit an ffmpeg `filter_complex` graph that
   concats segment videos, applies each joiner's transition, and overlays
   each segment's image/text layers at the right timestamps. Output:
   a single mp4.
5. **Concatenate audio**: per segment, select original / replaced / silence.
   Concat in lockstep with video. Phase 2 mixes audio beds on top.
6. **Concatenate funscripts**: for each selected output channel, load
   each segment's funscript for that channel, shift all `at` timestamps
   by the segment's running start, and concat. Actions that fall in
   joiner gaps are dropped (v1: hold last position; Phase 2: synthesize
   via a FunscriptForge transform).
7. **Write chapter markers**: one chapter per segment in the output mp4
   (ffmpeg `-metadata` chapters) and as `chapters` array in each output
   funscript.
8. **Write project JSON** alongside output for reproducibility.
9. **Generate heatmap + beatmap preview** PNGs per channel.

## ffmpeg filter-complex approach

Segments concatenate with the `concat` filter (not the demuxer):

```
[0:v]scale=1920:1080,setsar=1[v0];
[1:v]scale=1920:1080,setsar=1[v1];
[v0][0:a][v1][1:a]concat=n=2:v=1:a=1[vout][aout]
```

For a fade-to-black joiner we prepend a black clip + use `xfade`:

```
[v0][v1]xfade=transition=fadeblack:duration=2:offset=X[vout]
```

For overlays within a segment, we pre-apply before concat:

```
[v0][1:v]overlay=x=(W-w)/2:y=(H-h)/2:enable='between(t,0.5,3)'[v0_with_logo]
```

Text uses `drawtext`. Alpha masks for the "letters revealing next frame"
effect use `alphamerge`.

Codec, FPS, and resolution mismatches: v1 assumes clips match. If
ffprobe shows a mismatch, we emit a warning and let ffmpeg re-encode.
Phase 2 adds an explicit "normalize" pre-pass.

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

```
forgeassembler/
├── forgeassembler.py              # PyWebView launcher (dual-mode)
├── ui.py                           # Streamlit UI, three tabs
├── cli.py                          # argparse CLI entry point
├── forgeassembler_core/
│   ├── __init__.py
│   ├── about.py                    # version + credits
│   ├── project.py                  # Project model, load/save JSON, validate
│   ├── detect.py                   # folder → video + funscripts
│   ├── layout.py                   # compute running timeline
│   ├── concat_video.py             # ffmpeg video concat + overlays
│   ├── concat_funscript.py         # funscript timestamp shift + concat
│   ├── joiners/
│   │   ├── __init__.py
│   │   ├── base.py                 # Joiner ABC
│   │   ├── none_joiner.py          # straight cut
│   │   └── fade_to_black.py        # fade/hold/fade
│   ├── overlays/                   # image + text overlay builders
│   ├── chapters.py                 # mp4 chapter markers
│   ├── heatmap.py                  # preview generation
│   └── forge.py                    # the top-level forge() orchestrator
├── tests/                          # pytest
│   ├── fixtures/                   # tiny test videos + funscripts
│   ├── test_project.py
│   ├── test_detect.py
│   ├── test_layout.py
│   ├── test_concat_funscript.py
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

```
forgeassembler forge <project.json>         # run a saved project
forgeassembler detect <folder>              # preview what auto-detects in a folder
forgeassembler validate <project.json>      # schema + resolvability check, no forging
forgeassembler list-joiners                 # show joiner types and params
forgeassembler --version
```

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

- Segments with video + audio options + image overlays + text overlays
- Joiners: None, FadeToBlack
- Output channels: main, multi-axis, 3-phase estim
- Project JSON save/load
- Chapter markers (mp4 + funscript)
- Heatmap + beatmap preview
- Summary stats in sidebar
- Error handling: missing variant prompt, corrupt video skip
- CLI: `forge`, `detect`, `validate`, `list-joiners`
- Tests: unit + CLI + 1-2 integration fixtures

### Phase 2

- TitleCard joiner built with the template DSL
- Per-segment trim ranges (HH:MM:SS.mmm)
- Per-segment bookmark text
- Audio estim WAV concat (resample to common rate)
- Pulse frequency + 4-phase estim
- Transform-based funscript fill during joiner gaps
- YAML template DSL (Option B) + 5-10 preset templates
- Project-level audio beds
- Reorder UI in the list panel

### Phase 3+

- Visual template editor
- Normalize-resolution-FPS pre-pass
- Video-on-video overlays (PIP)
- Batch mode from the UI (drop a folder of project.json files)
