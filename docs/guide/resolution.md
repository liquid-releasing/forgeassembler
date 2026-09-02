# Resolution and scaling

The **Resolution** setting on the Output tab decides the pixel size of the
combined video. Its real job is to put every clip on **one canvas** so they can
be joined at all — not to improve them.

!!! warning "ForgeAssembler resizes. It does not enhance."
    Choosing 4K on 1080p sources gives you a genuine 3840×2160 file with
    **exactly the detail the source had**, interpolated to fill four times as
    many pixels. There is no super-resolution, no sharpening, and no
    detail synthesis anywhere in ForgeAssembler. If you want real enhancement,
    do it **before** you import — with a tool built for it, such as Topaz Video
    AI — and assemble the enhanced files.

## Why a resolution setting exists at all

Concatenation needs every clip to share one frame size. A compilation of a
1920×1080 scene and a 1906×1080 scene cannot be stitched until both are the
same shape, so each clip is scaled to fit the chosen canvas and padded to fill
it exactly:

```
scale=<W>:<H>:force_original_aspect_ratio=decrease:flags=lanczos,
pad=<W>:<H>:(ow-iw)/2:(oh-ih)/2,
setsar=1
```

`force_original_aspect_ratio=decrease` means **aspect ratio is never
distorted** — a clip is scaled until it fits inside the canvas, then centred,
and whatever is left over becomes black bars.

!!! note "Odd source widths produce thin bars"
    A 1906×1080 source on a 1920×1080 canvas scales to 1906×1080 and gains a
    7-pixel black bar on each side. On a 4K canvas the same clip becomes
    3812×2160 with 14-pixel bars. The bars are **baked into the output**. If
    your sources are an unusual width and you want no bars, set the resolution
    to `source` (below), or crop them before importing.

## The scaler

Every resize uses **Lanczos** (`flags=lanczos`), not ffmpeg's default bicubic.
Lanczos is sharper in both directions — downscaling a 4K clip to 1080p and
upscaling a 720p clip to 1080p both come out crisper — and it costs nothing
measurable next to the encode.

This applies to the video, to scaled overlay images, and to clip thumbnails.

It is still a **resampler**. A sharper interpolation is not new detail.

## Choosing a value

| Setting | Canvas | Use it when |
|---|---|---|
| `source` | Matches the **first video clip** in the project | All your clips are the same size and you want no resampling at all |
| `1080p` | 1920×1080 | The common case |
| `1440p` | 2560×1440 | Sources are genuinely 1440p or larger |
| `4k` | 3840×2160 | Sources are genuinely 4K |
| `uw_1080p` / `uw_1440p` | 2560×1080 / 3440×1440 | Ultrawide sources |
| `4_3_hd` | 1440×1080 | 4:3 material |
| `3_4_hd` / `9_16_hd` | 1080×1440 / 1080×1920 | Vertical / phone-shaped output |

**Pick the resolution your sources actually are.** Upscaling costs real time and
disk for no visible gain:

- A 13-minute 1080p compilation forged at **1080p** was 812 MB at 8.2 Mbps.
- The same compilation forged at **4K** was **2.45 GB at 24.5 Mbps** — three
  times the size, three times the encode, and not one extra pixel of detail.

`source` skips the guesswork: ForgeAssembler probes the first video clip and
uses its dimensions as the canvas. Clips that already match are scaled by a
factor of exactly 1 — the cheapest, cleanest path. Note that `source` needs at
least one video clip to probe; a project of nothing but title cards has nothing
to measure.

## What about downscaling?

Downscaling is the case where the resolution setting genuinely helps. Taking 4K
sources to a 1080p output is a real quality operation — Lanczos downsampling
averages four pixels into one and the result is sharper and cleaner than the
source viewed at that size. Mixed-resolution projects are normalised the same
way, so a 4K clip and a 1080p clip end up visually consistent.

## Frame rate

Frame rate is separate and works the same way: `source` takes the first video
clip's rate, or you can force 24 / 30 / 60. Forcing a rate **resamples** the
timing — it does not interpolate new frames, so raising the number does not make
motion smoother.

## See also

- [GPU acceleration](gpu-acceleration.md) — which encoder does the work, and how
  much faster it is
- [Output channels](channels.md) — what gets written alongside the video
