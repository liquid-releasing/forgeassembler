# Getting Started: Black Card with Transparent Letter Cutouts

The dramatic version of a title card. You'll end with a **black PNG
whose letters are transparent holes**. When you drop it into
ForgeAssembler, the letters reveal whatever is behind the card — the
next clip, a held frame, a color, anything.

This is the "scope reveal" / "reverse silhouette" look common in film
trailers. Slightly more involved than a plain white title, but still
beginner-friendly.

If you've never used Figma before, follow every step. It assumes no
prior knowledge.

---

## What you need

- A free Figma account: [figma.com](https://www.figma.com/) → **Sign up**.
- A web browser.
- 20 minutes.
- (Recommended) Read [getting_started_white_on_transparent.md](getting_started_white_on_transparent.md)
  first for the basic Figma orientation.

---

## Step 1 — Create a new Figma file

1. Sign in and click the blue **+ Design file** button on your dashboard.
2. Rename the file at the top-left to `Title Cards — Black Cutout`.

---

## Step 2 — Create a frame at your target resolution

A **frame** is your fixed-size export boundary — pick one that matches
the output resolution you'll forge at.

1. Press **F** (Frame tool).
2. In the **right sidebar**, set **W** and **H** to the pixel size from
   the table below.
3. Click on the canvas to drop the frame.
4. Rename it in the **Layers panel** (left sidebar) — e.g. `Title / 1920x1080`.

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
| `9_16_hd` | 1080 × 1920 | 9:16 portrait (TikTok/Reels) |

If unsure, start with `1080p`.

---

## Step 3 — Fill the frame with pure black

1. Click the frame.
2. In the **right sidebar**, find the **Fill** section.
3. Click the fill color swatch and enter hex `000000`.
4. Confirm opacity is `100%`.

The frame is now a solid black rectangle.

---

## Step 4 — Add your title text on top of the black

1. Press **T** (Text tool).
2. Click in the center of the frame and type your title — e.g.
   `WILD RIDE`.
3. In the **right sidebar**:
   - **Font**: pick something bold. `Inter Black`, `Bebas Neue`, or
     `Montserrat Black` all look great cutout.
   - **Style**: choose the heaviest weight available (Black, ExtraBold).
   - **Size**: pick from this table and adjust to taste:
     - `1080p` → 200–280
     - `1440p` → 260–360
     - `4k` → 400–560
     - `uw_1080p` / `uw_1440p` → experiment — you have more horizontal space
     - `4_3_hd` → 160–220
     - `3_4_hd` / `9_16_hd` → 140–200
   - **Fill**: any color for now (white is easiest to see while you work).
     The fill will be replaced by transparency at the end.
   - **Alignment**: **Center**.

---

## Step 5 — Center the text on the frame

1. Select the text layer.
2. Hold **Shift** and click the frame so both are selected.
3. Use the alignment buttons at the top of the right sidebar —
   **Align horizontal centers** and **Align vertical centers**.

The text sits exactly centered on the black.

---

## Step 6 — Convert the text to vector outlines

The boolean "subtract" operation requires vector shapes, not live text.
This step flattens the text so the letters become paths. **Duplicate
the text layer first** so you can edit the wording later if needed.

1. Select the text.
2. Press **Ctrl/Cmd + D** to duplicate it.
3. Click the eye icon next to the **original** text layer in the Layers
   panel to hide it — this is your backup.
4. Select the **duplicate** text layer.
5. Right-click on the canvas and choose **Outline stroke** (or
   **Flatten selection**, depending on your Figma version — both work
   for pure fill text).

The duplicate is now a set of vector paths shaped like the letters. You
can confirm by looking at the Layers panel — its icon changes from a
"T" to a vector shape.

---

## Step 7 — Subtract the letters from the black frame

This is the magic step.

1. In the Layers panel, select **both** the black frame and the
   outlined text (hold **Ctrl/Cmd** and click each).
2. Look at the top toolbar for the **Boolean operations** icon — it
   looks like two overlapping squares. Click the dropdown arrow next
   to it.
3. Choose **Subtract selection**.

The black rectangle now has transparent letter-shaped holes in it. You
should see the canvas background (usually gray checkers) through the
letters.

If the result looks inverted (letters are black, everything else
transparent), you selected the order wrong. Press **Ctrl/Cmd + Z** to
undo and try again — in Figma's subtract, the **top** layer is
subtracted from the **bottom** layer. If your text is underneath the
frame, pull it up first.

---

## Step 8 — Export as a PNG with alpha

1. Click the frame in the Layers panel.
2. In the **right sidebar**, scroll to **Export** and click **+**.
3. Settings:
   - **Format**: `PNG`
   - **Scale**: `1x`
4. Click **Export** and save the file — e.g.
   `C:\Users\bruce\Videos\title_cards\wildride_1080p.png`.

Open the PNG in any image viewer that supports transparency (Windows
Photos, macOS Preview, Firefox). You should see a black rectangle with
transparent letter-shaped holes.

---

## Step 9 — Use it in ForgeAssembler

A cutout title card works best **over a second layer of something**,
since the letters are transparent holes. ForgeAssembler composites it
for you natively — you don't need to flatten the PNG against a reveal
image yourself.

### Via the UI

1. Launch ForgeAssembler.
2. Add the segment you want the cutout to appear *over* first (e.g. the
   preceding video clip).
3. On the **Build** tab, use **"Add a title card (PNG still)"**:
   - **PNG file** — the cutout PNG you just exported.
   - **Hold seconds** — how long the cutout should stay on screen
     (e.g. `2.5`).
   - **Background** — select **"Previous segment's last frame"**.
4. ForgeAssembler extracts the last frame of your preceding clip,
   composites the cutout PNG over it, and holds the result for the
   duration you picked. The transparent letter-holes reveal the frozen
   frame underneath.
5. Optionally add audio — a replacement MP3/WAV sting, or silence.
6. Forge.

### Via project JSON

A cutout-over-held-frame segment looks like this:

```json
{
  "id": "seg-reveal-1",
  "type": "segment",
  "video": "C:/Users/bruce/Videos/title_cards/wildride_1080p.png",
  "still_duration_s": 2.5,
  "background": "previous_last_frame",
  "audio": {
    "mode": "replace",
    "file": "C:/Users/bruce/Videos/title_cards/sting.mp3"
  }
}
```

The segment immediately before this one in the project's `items` list
supplies the frame that gets frozen behind the cutout letters.

### Why not just use a black background?

If you set `"background": "black"` (or leave it off — that's the
default), the transparent letters render as black against black and
you won't see the cutout at all. That mode is intended for the
white-on-transparent workflow covered in the
[companion guide](getting_started_white_on_transparent.md), where the
visible pixels *are* the text. For the scope-reveal effect of this
guide, always pair the cutout with `previous_last_frame`.

---

## Step 10 — Export more resolutions

1. Select your finished frame.
2. Press **Ctrl/Cmd + D** to duplicate it.
3. Click the duplicate and change **W** and **H** in the right sidebar
   to the next resolution.
4. The duplicate may distort — re-center and re-scale the cutout text
   until it looks balanced.
5. Export each frame as a separate PNG with a clear name.

---

## Troubleshooting

- **Subtract inverts the result (letters are black, rest transparent).**
  Layer order is swapped. Undo, move the text layer above the frame,
  and subtract again.
- **Exported PNG shows a solid black background with no visible
  letters.** The subtract didn't actually happen, or the letters are
  rendered in the same color as the background. Re-check Step 7.
- **Letters look jagged.** Figma's boolean at export is clean — if the
  PNG itself looks jagged, your viewer is displaying it at less than
  100% zoom. In the video output, it will be smooth.
- **Cutout shows black in the forged video, not a reveal.** You left
  the **Background** set to "Black" (or omitted it). Re-add the
  segment with **Background: Previous segment's last frame** (Step 9).
