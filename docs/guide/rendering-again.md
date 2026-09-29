# Rendering the same compilation twice

Most compilations want more than one video out of them. A 4K copy to keep and
watch, and a 1080p copy small enough to send to someone else, are the same
edit — the same scenes, the same joins, the same funscripts — rendered at two
sizes.

You do not rebuild anything to get the second one. You change two things on the
Output tab and press Forge again.

## The renders do not overwrite each other

Every video ForgeAssembler writes carries the size it was rendered at, just
before the extension:

```
Best Of.4k25.mp4
Best Of.1080p25.mp4
```

The tag is `<size><frame rate>`, and it reports what was **actually encoded** —
not what the setting said. If Resolution or Frame rate is set to `source`, the
value is read off your first clip at forge time and the tag names the result,
so you will never get a file called `Best Of.source.mp4`.

| Resolution setting | Tag at 25 fps |
| ------------------ | ------------- |
| 1080p              | `1080p25`     |
| 1440p              | `1440p25`     |
| 4k                 | `4k25`        |
| UW 1080p           | `uw1080p25`   |
| UW 1440p           | `uw1440p25`   |
| 4:3                | `4x3hd25`     |
| 3:4                | `3x4hd25`     |
| 9:16               | `9x16hd25`    |

Because the names differ, both renders sit in the output folder side by side
and neither replaces the other.

## Making the second render

On the **Output** tab:

1. Change **Resolution** to the size you want this time.
2. Under **Produce**, turn **off** everything except **Video (MP4)** —
   Funscripts, Haptic-estim audio, and `.forge scene`.

Then Forge as normal. You get one file: the video at the new size.

!!! tip "Turn the other outputs back on afterwards"
    Those switches are project settings, not settings for one render. If you
    leave them off, the next real forge will quietly skip the funscripts too.
    Turn them back on as soon as the second render finishes.

## Why the second render needs only the video

The funscripts, the haptic-estim audio and the `.forge` scene contain no
pixels. A stroke at 00:42:17 is at 00:42:17 whether the video around it is
1080p or 4K, and the chapter markers fall at the same moments either way.
Nothing in them changes with resolution, so a second copy would be identical
to the first — and writing it again only fills the folder with duplicates.

The video is the only output a resolution change actually affects.

## When the video-only shortcut does NOT apply

!!! danger "Only for resolution and frame rate — nothing else"
    The shortcut above is safe **only** when the two settings you changed are
    Resolution and Frame rate. If you changed anything that alters the
    timeline, turning the other outputs off will leave them describing a
    compilation that no longer exists.

Anything that changes *when* things happen needs a full forge, with every
output switched back on:

- adding or removing **branding** at either end
- adding, removing, reordering or retrimming **scenes**
- changing a **joiner** — a title card or a fade has a duration, so adding
  one moves everything after it
- changing a **section**'s contents

The reason is simple arithmetic. A 60-second branding bumper at the front
pushes every frame after it 60 seconds later. Measured on a real project:
chapter 1 started at 5,100 ms without branding and 65,100 ms with it. If you
re-render only the video, your funscripts still say 5,100 ms — so every
stroke in the compilation fires a minute early, for its entire length.

!!! tip "The rule in one line"
    Changed how it *looks*? Video only. Changed how *long* anything is?
    Forge everything.

## Adding branding to a compilation you already rendered

This is the common case of the rule above, and it works exactly as you would
hope: open the existing `.forgeproject`, set the branding at either end on
the Output tab, and forge.

A project saved before branding existed carries no branding settings at all,
and picks them up cleanly when you add them — nothing needs rebuilding and no
scene is touched. Leave **all** the Produce switches on, because the
timeline just moved.

The new render replaces the old one, since the size did not change and so
neither did the filename. That is safe: ForgeAssembler encodes to a temporary
file and only takes the real name once the render is complete, so if anything
goes wrong the previous render is still there. See
[Stopping a forge](stopping-a-forge.md).

### Save your branding once, reuse it everywhere

Branding is the one part of a compilation that is the same every time you
make one, and rebuilding it by hand for each project is how one release's
credits quietly end up saying something different from the last one's.

**Save branding…** on the Output tab writes a `.forgebranding` file holding

- the compilation's own title page,
- the `.forge` bumper at each end,
- the closing transition,
- and every compilation-level overlay — logo, credits, anchors and timing
  included.

**Load branding…** puts all of that into whatever project you have open. It
carries nothing else: no resolution, no frame rate, no folder, no sections. A
preset that silently reset your output resolution would be a trap, so it
cannot.

Loading **replaces** the branding that was there rather than merging with it.
A new intro with the old credits still over it is the shape of a mistake
nobody asks for, and nothing in the file could say which half you meant.

!!! tip "Adding branding to an old project"
    Open it, press **Load branding…**, forge. The render tag does not change,
    so the new file takes the same name as the old one — see the rule above
    about forging everything when the timeline moves.

## Which one to keep and which one to share

!!! warning "Rendering at 4K does not add detail"
    If your clips are 1080p, a 4K render is those same pixels interpolated to
    fill four times as many. It is a genuinely larger file and a genuinely
    sharper *scaler* — but there is no new detail in it. See
    [Resolution and scaling](resolution.md). Render 4K when your sources are
    4K, not to improve 1080p ones.

A rough guide:

- **Keep** the largest render your sources justify. This is the one you watch.
- **Share** 1080p. It plays everywhere, it uploads in a reasonable time, and
  on most screens the difference is invisible.

## Rendering several sizes from a script

ForgeAssembler does not queue renders. If you always want the same pair, a
three-line script is a better tool than a feature: it runs unattended, you
can schedule it, and it never forgets to turn the Produce switches back on.

`--resolution` and `--frame-rate` apply **to that run only** — your
`.forgeproject` is not modified, so the settings you see in the app stay
exactly as you left them.

=== "Windows (PowerShell)"

    ```powershell
    $p = "D:\releases\Best Of\best-of.forgeproject"

    # Everything: video, funscripts, estim audio, .forge scene.
    python cli.py forge $p --resolution 4k

    # Just the second video. The rest is resolution-independent,
    # so it is already correct from the run above.
    python cli.py forge $p --resolution 1080p `
        --no-funscripts --no-audio-estim --no-forge-bundle
    ```

=== "macOS / Linux"

    ```bash
    P="/media/releases/Best Of/best-of.forgeproject"

    python cli.py forge "$P" --resolution 4k

    python cli.py forge "$P" --resolution 1080p \
        --no-funscripts --no-audio-estim --no-forge-bundle
    ```

You end up with:

```
Best Of.4k25.mp4
Best Of.1080p25.mp4
Best Of.funscript          + the per-device folders
Best Of.forge
```

!!! note "Run the full pass first"
    Order matters only in that the funscripts, estim audio and `.forge` scene
    have to be written once. Do the full render first and the video-only
    passes after, in whatever order you like.

Every option is listed in [the CLI reference](cli.md).

## Checking the second render

Open the **Viewer** tab and use **Open output…** to point at the new file. The
Viewer reads what is actually on disk rather than what the project says should
be there, which is how you catch a render that came out at the wrong size or
stopped early.

The channel lanes and chapter bars come from the `.forge` scene, so they will
show the ones written by your **first** render — which is correct. The
funscripts and chapters did not change; only the pixels did.
