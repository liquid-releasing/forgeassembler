# CLI

ForgeAssembler ships with a command-line entry point alongside the
desktop app. Useful for batch jobs, headless servers, scripted
pipelines, or when you already have a `project.forgeproject.json` and
just want to render it without opening the UI.

## Invocation

From a checkout / venv:

```
python cli.py <command> [options]
```

From the bundled desktop install: the `forgeassembler` executable
accepts the same arguments as a CLI when invoked from a terminal
(it auto-detects whether to launch the GUI or run a CLI command).

## Commands

### `forge` — render a project

Run a saved project end-to-end: concat video, concat funscript
channels, emit MP4 chapter markers, save outputs to the project's
output folder.

```
python cli.py forge <project.json>
                    [--output DIR]
                    [--basename NAME]
                    [--no-video]
                    [--no-funscripts]
                    [--no-audio-estim]
```

Flags:

- `--output DIR` — override the project's `output.folder`.
- `--basename NAME` — override `output.basename` (the file stem; the
  engine appends `.mp4`, `.funscript`, etc.).
- `--no-video` — skip the video pipeline.
- `--no-funscripts` — skip the funscript pipeline.
- `--no-audio-estim` — skip per-channel haptic-estim audio concat
  (otherwise emits one `.stereostim.wav` / `.legacy.wav` /
  `.prostate.stereostim.wav` per channel found alongside source clips).

Useful for preflighting a render to disk-only or audio-only without
toggling settings in the UI.

### `new-project` — scan subfolders into a starter project

Walks a parent folder, treats each immediate subfolder as a section
with one segment, joins them with `none` (cut), and writes a starter
JSON.

```
python cli.py new-project <folder> <output.json>
                          [--output-folder DIR]
                          [--basename NAME]
                          [--resolution 1080p]
```

Mirrors the `.forge/0/0.mp4`, `.forge/1/1.mp4`, … folder convention
used by FunscriptForge / forgegen output. Produces a project you can
open in the UI for further editing.

### `detect` — show what auto-detects in a folder

Lists every video stem the detector found in the given folder, plus
the funscripts it found alongside each video.

```
python cli.py detect <folder>
```

Useful for sanity-checking that your funscript files match the video
stems before adding them to a project.

### `validate` — check a project without forging

Runs the validation pass that the UI uses (and that `forge` runs
implicitly), reports errors and warnings, exits non-zero on errors.

```
python cli.py validate <project.json>
```

CI-friendly. Use it as a pre-merge gate to catch malformed projects
before they hit a render queue.

### `list-joiners` — list available joiner types

Dumps every joiner type the engine knows about, with descriptions
and parameter schemas. Use to see what `joiner_type` strings are
valid in a hand-edited project JSON.

```
python cli.py list-joiners
```

### `--version`

```
python cli.py --version
```

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | validation error (bad project structure) |
| 2 | resolution error (missing file, corrupt video) |
| 3 | ffmpeg error |

These map to typical CI pre-/post-flight gates: 0 = ship, 1/2 = your
config is wrong, 3 = the system / environment broke.

## Common recipes

**Render a project saved from the UI:**

```
python cli.py forge ~/Videos/forgeassembler/combined.forgeproject.json
```

**Headless preflight (validate + render funscripts only):**

```
python cli.py validate combined.forgeproject.json && \
python cli.py forge combined.forgeproject.json --no-video
```

**Bootstrap a project from a folder of pre-split clips:**

```
python cli.py new-project ./test_media/victoriaoats/.forge \
                          ./victoriaoats.forgeproject.json
python cli.py validate ./victoriaoats.forgeproject.json
python cli.py forge ./victoriaoats.forgeproject.json
```
