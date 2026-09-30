# Stopping a forge

A forge is the longest thing ForgeAssembler does. A two-hour compilation at
4K takes the better part of an hour, and sometimes you realise five minutes
in that you picked the wrong resolution.

There is a right way to stop one, and a way that can cost you a finished
render. This page covers both.

## Cancel

While a forge runs, a **Cancel** button sits next to *Forging…* on the Forge
tab. Press it and the render stops within a second or two.

**Your previous render is safe.** ForgeAssembler encodes to a temporary file
and only gives it its real name once the encode finishes. So if you forged
`Best Of.4k30.mp4` last night and cancel a new run today, last night's file
is still there, untouched and complete. Cancelling costs you only the run you
cancelled.

The app will say so:

> Forge cancelled. Nothing was written — any earlier render in the output
> folder is untouched.

### What Cancel leaves behind

One partial file, in your output folder, named like this:

```
Best Of.4k30.tmp.9164.mp4.part
```

Three things mark it as unfinished: `tmp`, the number of the process that was
writing it, and the `.part` on the end. **It is safe to delete, and you
should.** It is not a usable video — it stops wherever the encode had got to.

The `.part` ending is deliberate. It is the same convention web browsers use
for a download in progress, and it means the file is not a video as far as
your computer is concerned: it gets no video icon, nothing offers to play it,
and a batch upload or a "copy all the MP4s" step will skip it. An earlier
version of ForgeAssembler left these ending in `.mp4`, which put something
that looked exactly like a finished render right next to the real ones.

ForgeAssembler deletes any it finds — in either spelling — the next time you
forge, so an old one left over from before this change will be cleared for
you.

ForgeAssembler clears it for you the next time you forge **to the same size**
— a new 4K render sweeps old 4K leftovers. It does not sweep leftovers from a
different size, because it cannot safely tell those apart from a render
someone else is making right now. So a cancelled 4K run followed by a 1080p
run leaves the 4K leftover in place.

## Closing the app does not stop the forge

!!! danger "This is the one that costs you a render"
    Closing the ForgeAssembler window, or using **End task** in Task Manager,
    **does not stop a forge that is running.** The work carries on with
    nothing watching it.

ForgeAssembler does not do the encoding itself. It starts two other programs
— a converter and `ffmpeg` — and watches them. The window is a view onto the
work, not the work itself. Close the window and those two programs are still
there, still reading your clips, still writing to your output file.

Nothing on screen tells you this, because there is no longer anything on
screen.

### Why it matters

Suppose you close the app mid-forge, reopen it, and forge again. You now have
**two** encoders writing to the same output file at the same time. Neither
knows about the other. The result is a file that keeps growing, often to
several gigabytes, and then will not play in anything — the index that tells
a player where everything is never gets written.

That has happened. It cost a 5.33 GB file and the entire render had to start
again.

### How to tell whether a forge is still running

Open **Task Manager** (Ctrl+Shift+Esc), choose the **Details** tab, and sort
by name. Look for:

- **`ffmpeg-win-x86_64-v7.1.exe`** — this is the encoder. If it is there and
  using significant memory or CPU, a render is in progress.
- **`forge-cli.exe`** — ForgeAssembler's engine. In a development build this
  appears as `python.exe` instead.

!!! warning "It is not called `ffmpeg.exe`"

    The encoder ships inside ForgeAssembler rather than coming from your
    system, and it keeps its full build name. Sorting Task Manager and
    looking for a plain `ffmpeg.exe` finds nothing **even while a forge is
    running** — searching for `ffmpeg` as a fragment is what works.

    This is not hypothetical: that exact mistake is how the 5.33 GB file
    above got destroyed. The check said "nothing running", and something was.

The engine also outlives the encoder between stages — it writes funscripts
and audio after the video is done — so `forge-cli.exe` on its own still means
a forge is in progress. Only when **neither** is present are you safe.

### How to stop one that is already orphaned

In Task Manager, right-click `forge-cli.exe` (or `python.exe`) and choose
**End process tree** — not *End task*. The tree matters: `ffmpeg` is started
*by* the engine, so ending only the engine leaves `ffmpeg` running and still
writing. It is the same trap in a different costume.

If you prefer the command line, this does the same thing:

```powershell
# Find the engine's process ID
Get-Process forge-cli, python -ErrorAction SilentlyContinue | Select-Object Id, Name

# Stop it and everything it started
taskkill /T /F /PID <the id>
```

`/T` is the part that matters. Without it you kill the engine and leave the
encoder behind.

Afterwards, delete any `tmp` file left in the output folder, as above.

!!! tip "Use Cancel instead"
    Cancel does all of this correctly, including stopping `ffmpeg`. Reach for
    Task Manager only when the app is not responding.

## Which files a stopped forge affects

| File | After a cancel |
| ---- | -------------- |
| A previous render of the same name | Untouched and complete |
| The render you cancelled | Never created under its real name |
| `…tmp….mp4.part` | Left behind; delete it |
| Funscripts, haptic audio, `.forge` scene | Whatever had already been written stays |

The last row is worth knowing. A forge runs its stages in a fixed order —
video, then funscripts, then haptic-estim audio, then the `.forge` scene —
and the video is around **80% of the total time**. So a cancel almost always
lands during the video, when none of the other outputs have been written yet
and there is nothing half-finished to worry about.

If you cancel late, in the last fifth of the bar, you may end up with some of
those outputs and not others. There is no harm in it, but do not assume the
set is complete. Forge again rather than trusting a partial one — and if only
the video needs redoing, [Rendering the same compilation
twice](rendering-again.md) shows how to re-render it on its own.
