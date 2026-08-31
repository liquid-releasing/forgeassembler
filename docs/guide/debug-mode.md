# Debug Mode

Debug mode turns on lightweight instrumentation that records what
you did in a session — project loads, forge clicks, forge completions
or failures — and lets you mark specific moments when something
looked wrong. The output is a single JSONL file you can attach to a
bug report.

## Turning it on

Scroll to the bottom of the sidebar and tick **🔧 Debug mode**. An
event panel expands below it.

The panel shows:

- A running count of events captured this session
- A **⚑ Mark this as an issue** button
- An **Export debug log** button

Debug mode is a no-op when off, so you can leave it on for a while
without any performance cost.

## What gets recorded

Only these events — not keystrokes, not project contents, not media:

- `project_load_json` — you loaded a project from a file
- `new_project_clicked` — you started a fresh project
- `forge_clicked` — you pressed Forge, with a hash of the project
  state plus section count and channel list
- `forge_funscripts_done` / `forge_video_done` — a pipeline stage
  completed cleanly
- `forge_funscripts_failed` / `forge_video_failed` — a pipeline
  stage raised, with the exception message

Each event has a timestamp and a simple payload. No file paths get
stored verbatim — paths are hashed for privacy.

## Marking a specific issue

When you see something wrong (wrong volume, missing overlay, a UI
glitch, anything), click **⚑ Mark this as an issue**. You'll be
prompted for a one-line description.

The mark becomes its own event in the log next to whatever you just
did. When you're ready to report, the marks are the bookmarks that
help us (or you) re-read the session.

Rule of thumb: one ⚑ per observed problem, in the moment. Don't try
to retroactively describe; let the nearby events carry the context.

## Exporting the log

Click **Export debug log**. You get a JSONL file in
`~/.forgeassembler/debug_logs/` named with the session start time.
Copy the file to wherever you're reporting the issue.

JSONL is one-event-per-line JSON. Each line is human-readable.
Example:

```json
{"t": 1713709200.112, "event": "forge_clicked", "hash": "ab12…", "sections": 3, "channels": ["main", "multi_axis", "prostate"]}
{"t": 1713709210.882, "event": "mark", "description": "Section 2 narration too quiet"}
{"t": 1713709222.001, "event": "forge_video_done", "duration_s": 22.1}
```

## What to include in a bug report

1. The debug log JSONL (mandatory)
2. A short description of what you expected vs what happened
3. The project JSON if you're willing to share it (strip media
   paths if you're paranoid; they're already hashed in the log)
4. OS + app version (see About dialog → Help menu)

File the report on
[the ForgeAssembler issue tracker](https://github.com/liquid-releasing/forgeassembler/issues)
or drop it in the
[Liquid Releasing Discord](https://discord.gg/UHdJFhEZF).

## When NOT to use debug mode

If you already know the fix is a settings tweak (volume too low,
wrong position, etc.), just fix it — you don't need to report every
minor adjustment. Debug mode pays off when:

- Something unexpected happens and you want a second forge to
  confirm it's reproducible
- You're about to report a crash, missing output, wrong output
- You want to keep a record of exactly what you tested during a
  long session

---

That's the whole user guide. Come back to
**[Getting Started](getting-started.md)** if you need the
quick-reference pointers.
