# Sci-Fi Cockpit Title Card — End-to-End Example

A complete, reproducible example of a "sci-fi cockpit HUD" title card:
neon outlined text, soft glow, a faint micro-grid overlay, and thin
accent bars. The finished output is a **transparent PNG** you drop
into ForgeAssembler as a segment.

This doc is still novice-friendly — every step tells you exactly what
to click — but the result is more elaborate than the
[white-on-transparent](getting_started_white_on_transparent.md) and
[black-cutout](getting_started_black_cutout.md) starter cards. Read
one of those first if this is your first time in Figma.

---

## What you'll build

A single title card, exported at one or more of ForgeAssembler's
supported resolutions, with:

- Transparent background
- Large bold title text with a **cyan neon outline**
- Soft **cyan drop-shadow glow** around the text
- Faint **micro-grid** overlay across the frame (optional)
- **Magenta accent bars** above and below the title (optional)

---

## What you need

- A free Figma account: [figma.com](https://www.figma.com/).
- A web browser.
- 30–45 minutes.

---

## Step 1 — Create a new Figma file

1. Sign in and click **+ Design file** on your dashboard.
2. Rename the file at top-left to `Title Cards — Sci-Fi Cockpit`.

---

## Step 2 — Create a frame at your target resolution

1. Press **F** (Frame tool).
2. In the **right sidebar**, set **W** and **H** to your target pixel
   size from the table below.
3. Click on the canvas to drop the frame.
4. Rename it in the **Layers panel** — e.g. `SciFi / 1920x1080`.
5. Remove the frame's fill: in the **right sidebar Fill** section,
   click the eye icon to hide it (we want transparency).

### ForgeAssembler resolutions

| Name in ForgeAssembler | Width × Height | Aspect |
|---|---|---|
| `1080p` (default) | 1920 × 1080 | 16:9 |
| `1440p` | 2560 × 1440 | 16:9 |
| `4k` | 3840 × 2160 | 16:9 |
| `uw_1080p` | 2560 × 1080 | 21:9 UltraWide |
| `uw_1440p` | 3440 × 1440 | 21:9 UltraWide |
| `4_3_hd` | 1440 × 1080 | 4:3 |
| `3_4_hd` | 1080 × 1440 | 3:4 portrait |
| `9_16_hd` | 1080 × 1920 | 9:16 portrait |

UltraWide and 16:9 sizes give you the most room for this HUD look.
The portrait sizes work — just plan on more vertical stacking and
smaller accent bars.

---

## Step 3 — Define your color palette

These hex codes are the cockpit theme. You can paste them verbatim or
adapt.

| Name | Hex | Used for |
|---|---|---|
| Cyan Primary | `#00E5FF` | Title outline, glow, grid |
| Magenta Accent | `#FF2BF0` | Accent bars, secondary highlights |
| HUD White | `#F2F2F2` | Title fill color |
| Grid Cyan | `#00E5FF` at 6–12% opacity | Micro-grid lines |

You'll apply these as **Fills** and **Strokes** on specific layers.
No need to create Figma Color Styles unless you want to reuse them
across many files.

---

## Step 4 — Add the title text

1. Press **T** (Text tool).
2. Click near the center of the frame and type your title —
   `NIGHT RUN`, `INTERCEPT`, `WILD RIDE`, etc.
3. In the **right sidebar**:
   - **Font**: `Inter` (weight **Bold** or **Black**) works. Fancier
     picks: `Orbitron` or `Rajdhani` (both free on Google Fonts, added
     via **Text styles → Browse fonts**).
   - **Size**:
     - `1080p` → 180–240
     - `1440p` → 240–320
     - `4k` → 360–480
     - UltraWide sizes → 200–280
     - Portrait sizes → 140–200
   - **Alignment**: Center.
   - **Letter spacing**: bump slightly — around `+20` to `+40` units —
     for a more technical feel.
4. **Fill**: `#F2F2F2` (HUD White).

Center the text on the frame: select both text and frame (**Shift +
click**), then use the alignment buttons in the right sidebar
(**Align horizontal centers**, **Align vertical centers**).

---

## Step 5 — Add the neon outline

1. With the text selected, in the right sidebar scroll to **Stroke**.
2. Click the **+** to add a stroke.
3. Stroke color: `#00E5FF` (Cyan Primary).
4. Stroke width:
   - `1080p` → 4–6 px
   - `1440p` → 6–8 px
   - `4k` → 8–12 px
   - Scale proportionally for other sizes.
5. Click the **three-dot** icon next to the stroke width to open stroke
   options. Set **Position** to `Outside` (looks best on title text).

The text should now look like bright white letters with a cyan edge.

---

## Step 6 — Add the soft cyan glow

1. With the text still selected, scroll to **Effects** in the right
   sidebar.
2. Click **+** to add an effect. It defaults to `Drop shadow`.
3. Click the sun icon next to it to open shadow settings:
   - **Color**: `#00E5FF` at `40%` opacity.
   - **X offset**: `0`
   - **Y offset**: `0`
   - **Blur**: `12` (scale up for larger resolutions — try `24` for
     4k).
   - **Spread**: `0`
4. Click **+** again to add a **second** drop shadow (for a wider
   bloom):
   - **Color**: `#00E5FF` at `20%` opacity.
   - **Blur**: `32` (or `64` for 4k).

Two stacked shadows give a close, intense glow plus a wider soft bloom.

---

## Step 7 — Add magenta accent bars (optional)

Two thin bars — one above, one below the title — selling the HUD feel.

1. Press **R** (Rectangle tool).
2. Draw a thin rectangle across most of the frame width above the
   title. Size:
   - Height: `4–8 px` (scale up for 4k).
   - Width: roughly 60–80% of the frame width.
3. **Fill**: `#FF2BF0` (Magenta Accent) at `100%`.
4. Add an **Effect** → `Drop shadow`:
   - **Color**: `#FF2BF0` at `30%`
   - **Blur**: `24`
5. Duplicate the bar (**Ctrl/Cmd + D**) and move the copy below the
   title.
6. Use the alignment buttons to center both bars horizontally on the
   frame.

Tune vertical position so the bars frame the title without crowding.

---

## Step 8 — Add the micro-grid overlay (optional)

The tiny cyan grid sells the cockpit aesthetic. It's time-consuming in
Figma; skip this step for a first pass.

1. Press **R** (Rectangle tool).
2. Draw a **32 × 32 px** square in a corner of the frame.
3. Remove the fill (eye icon).
4. Add a **1 px stroke**, color `#00E5FF`, opacity `6%`.
5. Duplicate this square horizontally and vertically until it tiles
   across the frame. Figma's **Ctrl/Cmd + D** remembers the last
   duplicate direction and offset — use it after the second square to
   repeat along a row.
6. Once one row is tiled, select the whole row, duplicate it downward
   and repeat.
7. Group all grid squares (**Ctrl/Cmd + G**) and name the group
   `Micro-Grid`.
8. Lock the group by clicking the lock icon in the Layers panel — now
   you can work on top of it without nudging it.

**Faster alternative:** use Figma's **Layout grid** feature on the
frame. In the right sidebar under **Layout grid**, click **+** and add
a Grid style with size `32 px` and color `#00E5FF` at `6%` opacity.
This produces a visible grid in the editor but **does not export**
with the frame. Use real rectangles if you want the grid baked into
the PNG.

---

## Step 9 — Export as a transparent PNG

1. Click the frame in the Layers panel.
2. In the right sidebar, scroll to **Export** and click **+**.
3. Settings:
   - **Format**: `PNG`
   - **Scale**: `1x`
4. Click **Export**. Save as — for example —
   `C:\Users\bruce\Videos\title_cards\nightrun_1080p.png`.

Check the PNG in an image viewer: the background should be
transparent, the title glowing cyan, the accent bars sharp, and the
grid subtle (or absent if you skipped Step 8).

---

## Step 10 — Use it in ForgeAssembler

A title card is just a segment whose video is a PNG.

### Via the UI

1. Launch ForgeAssembler.
2. On the **Build** tab, click **Add segment** and point at the PNG.
3. Set **Still duration (seconds)** — `3.0` is a solid default.
4. **Audio**: pick **Silence** for a clean reveal, or **Replace with
   file** and point at an MP3/WAV sting.
5. Add a `fade_to_black` joiner before and/or after for transitions.
6. Forge.

### Via project JSON

```json
{
  "id": "seg-scifi-1",
  "type": "segment",
  "video": "C:/Users/bruce/Videos/title_cards/nightrun_1080p.png",
  "still_duration_s": 3.0,
  "audio": {
    "mode": "replace",
    "file": "C:/Users/bruce/Videos/title_cards/nightrun_sting.mp3"
  }
}
```

### Notes on background

This card has a transparent background. ForgeAssembler Phase 1 treats
the PNG as the segment's base video, so transparent areas become
**black** in the output. That's usually exactly right for a cockpit
title — the glow reads against black.

If you want the cockpit title *over* moving footage instead, flatten
the PNG onto a still frame in an image tool before importing (see the
[black-cutout doc](getting_started_black_cutout.md) Step 9 for the
same technique). True live overlay-on-video is a Phase 2 feature.

---

## Step 11 — Make a reusable template (optional)

Once you like the result, lock in the styles for reuse:

1. Group everything inside the frame (**Ctrl/Cmd + G**) and name the
   group `TitleGroup`.
2. Select the frame and press **Ctrl/Cmd + Alt + K** to turn it into a
   **component**. Name it `SciFi / 1920x1080`.
3. To make more titles at the same resolution: drag the component out
   of the Assets panel (left sidebar), then double-click the text inside
   the instance and type a new title. The stroke, glow, and grid stay
   consistent.
4. For other resolutions, duplicate the component, resize the frame,
   and rescale text/stroke/glow proportionally.

---

## Troubleshooting

- **Text looks flat, no glow.** Effects aren't enabled. Go back to
  Step 6 and confirm both drop shadows are added and visible (click
  the eye icon in the Effect row if needed).
- **Stroke is inside the letters, not outside.** You missed Step 5's
  "Position: Outside" setting. Click the three-dot icon next to the
  stroke width.
- **PNG exports with a color background.** The frame's fill wasn't
  removed in Step 2. Fix the fill on the frame (not the text).
- **Glow is cut off at the frame edges.** Your glow blur extends
  beyond the frame's bounds. Either reduce the blur or add padding by
  resizing the frame larger.
- **Micro-grid is visible in Figma but missing from export.** You used
  the Layout Grid feature (which doesn't export). Redo with actual
  rectangles (Step 8).
