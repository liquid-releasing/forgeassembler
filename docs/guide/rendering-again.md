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

## Checking the second render

Open the **Viewer** tab and use **Open output…** to point at the new file. The
Viewer reads what is actually on disk rather than what the project says should
be there, which is how you catch a render that came out at the wrong size or
stopped early.

The channel lanes and chapter bars come from the `.forge` scene, so they will
show the ones written by your **first** render — which is correct. The
funscripts and chapters did not change; only the pixels did.
