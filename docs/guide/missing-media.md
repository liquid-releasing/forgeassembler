# When media goes missing

A project file stores **absolute paths** to your clips. That is the right
choice for a tool whose footage comes off several drives at once — but it
means a project is only as portable as the paths inside it, and two perfectly
ordinary things break them:

- **a folder moved** — you tidied up, or renamed a parent folder
- **the drive letter changed** — the same external drive is `D:` on one
  machine and `E:` on another

Nothing is lost when this happens. The project still knows every trim, every
joiner, every overlay. It just needs to be told where the files went.

## You are told on open

Open a project whose media has moved and a banner appears under the tab
strip. It stays until the problem is fixed, because it describes the state of
the project rather than announcing an event.

It says which of the three situations you are in, because they have different
fixes:

| what it says | what happened |
| --- | --- |
| *All 40 files this project uses are missing… every one of them is on `D:/`* | the drive came up under a different letter |
| *5 files are missing. All of them were under `D:/…/Session`* | that one folder moved |
| *3 files are missing. They are in different places* | they did not move together |

Clips whose video is gone are also marked on the Build canvas: a warning
border, an unlink icon, and **MISSING** where the duration usually sits. Hover
one to see the path it is looking for.

!!! note "A blank thumbnail is not the same thing"

    A clip can show no picture because the thumbnail has not been extracted
    yet, or because ffmpeg could not decode that frame. Those look different
    from a missing file, on purpose — a blank thumbnail used to be the only
    sign of all of these at once, which made it a sign of nothing.

## Fixing a folder that moved

Press **Find missing media…** in the banner. It asks for one thing: where the
folder went. Everything that lived under the old folder is re-pointed in a
single step.

It checks before it commits. If the folder you picked does not actually
contain the files, nothing is changed and it says so — a relink that
cheerfully rewrote forty paths onto forty files that are also not there would
be worse than one that failed.

Afterwards it re-reads the disk rather than assuming it succeeded, so the
banner always agrees with reality. If some files were found and others were
not, it tells you both numbers.

## Fixing one file

A file that moved on its own — most often because it was **renamed** — cannot
be followed by any amount of path arithmetic. Open that clip and use
**Find this file…**, which is the primary button whenever that clip is the
missing one.

This is also how you deliberately point a clip at a different video: the same
action is called **Replace video…** when nothing is wrong.

Relinking changes the path and nothing else. Trims, audio mode, colour,
overlays and channel selections all survive — you are telling the project
where a file went, not re-importing it.

## Forging with files missing

You cannot, and that is deliberate. ForgeAssembler validates before it
encodes and refuses to start, because the alternative is discovering the
problem forty minutes into a render.

Before this check existed the only symptom was a blank thumbnail and some
lines in a log nobody reads, so a project could look perfectly healthy
through an hour of editing and then refuse at the very end.

---

Next: **[Rendering again](rendering-again.md)** — what needs a full forge and
what only needs the video.
