# Getting Started: White Text on a Transparent Background

The simplest title card. You'll end with a **transparent PNG** whose only
pixels are the white title letters. When you drop it into ForgeAssembler,
the video behind it shows through the empty space — ideal for lower-third
captions, section headers, and clean overlay titles.

If you've never used Figma before, follow every step. It assumes no prior
knowledge.

---

## What you need

- A free Figma account: [figma.com](https://www.figma.com/) → **Sign up**.
- A web browser. Figma runs in the browser; no installation required.
- 15 minutes.

---

## Step 1 — Create a new Figma file

1. After signing in, click the blue **+ Design file** button in the top
   right of your dashboard.
2. A blank canvas opens. In the top-left corner, click the file name
   (it says **"Untitled"**) and rename it `Title Cards — White on Transparent`.

You are now inside Figma's **canvas**. The big empty gray area is where
you work. The **right sidebar** contains properties for whatever is selected.
The **left sidebar** (Layers panel) lists everything in your file.

---

## Step 2 — Create a frame at your target resolution

A **frame** in Figma is like a slide in PowerPoint — it has a fixed size
and acts as the export boundary. You create one frame per title card
resolution.

1. Press **F** on your keyboard (the Frame tool).
2. In the **right sidebar**, under **Frame**, you'll see **W** (width)
   and **H** (height). Click each and type the pixel size for your chosen
   resolution.
3. Click anywhere on the canvas to drop the frame.

Pick from the resolutions below. You can make one frame now and copy it
for other sizes later, or make all of them up front.

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

Match the frame to the output resolution you plan to forge at. If you're
unsure, start with `1080p` (1920 × 1080).

After creating the frame, rename it in the **Layers panel** (left
sidebar) to something descriptive — e.g. `Title / 1920x1080`.

---

## Step 3 — Make the frame's background transparent

By default a new frame has a white fill. You don't want that — the
whole point of this card is that the background is empty.

1. Click the frame in the canvas (or in the Layers panel).
2. In the **right sidebar**, find the **Fill** section.
3. Click the small **eye icon** on the fill row to hide it, or click the
   **minus sign** to remove the fill entirely.

The frame now shows a checkered pattern. That's Figma's way of saying
"transparent." Good.

---

## Step 4 — Add your title text

1. Press **T** (Text tool).
2. Click roughly in the middle of the frame and type your title text —
   for example, `CHAPTER 1`.
3. In the **right sidebar**:
   - **Font**: pick something bold and simple. `Inter` (Figma's default)
     or `Montserrat` are good starts.
   - **Style/Weight**: choose **Bold** or **Black** for impact.
   - **Size**: start with the number from this table, then adjust by eye:
     - `1080p` → 180–240
     - `1440p` → 240–320
     - `4k` → 360–480
     - `uw_1080p` / `uw_1440p` → size to taste; you have more horizontal room
     - `4_3_hd` → 140–200
     - `3_4_hd` / `9_16_hd` → 120–180
   - **Alignment**: set to **Center** (the middle icon in the alignment row).
4. Set the text **Fill** color to pure white: click the fill swatch,
   type `FFFFFF` in the hex field.

---

## Step 5 — Center the text in the frame

1. Click the text layer.
2. Hold **Shift** and click the frame (so both are selected), OR use the
   alignment buttons at the top of the right sidebar.
3. Click **Align horizontal centers** and **Align vertical centers** (the
   two middle icons in the alignment row).

The text is now exactly centered in the frame.

---

## Step 6 — Export as a transparent PNG

1. Click the **frame** (not the text) in the Layers panel or on the canvas.
2. In the **right sidebar**, scroll to the bottom. Find the **Export**
   section.
3. Click the **+** next to **Export**.
4. Settings:
   - **Format**: `PNG`
   - **Scale**: `1x` (you already set exact pixels in Step 2)
5. Click the **Export** button that appears.
6. Save the file somewhere you'll find it — e.g.
   `C:\Users\bruce\Videos\title_cards\chapter1_1080p.png`.

Because you hid the frame's fill in Step 3, the exported PNG has a
transparent background. Open it in any image viewer and the area around
the text will be the checkered transparency pattern (or actually empty,
depending on the viewer).

---

## Step 7 — Use it in ForgeAssembler

A title card in ForgeAssembler is just a **segment** whose video is a PNG.

### Via the UI

1. Launch ForgeAssembler.
2. On the **Build** tab, click **Add segment** and point at your PNG file.
3. ForgeAssembler detects it's a still and asks for **Still duration
   (seconds)** — enter how long the title should hold on screen (e.g. `3.0`).
4. **Audio**: a PNG has no audio of its own, so set the audio mode:
   - **Silence** — dead silence under the title card.
   - **Replace with file** — pick an MP3 or WAV (voiceover, music sting).
5. Insert a **Joiner** after it (e.g. `fade_to_black` with
   `duration_s: 1.0`) to transition into the next segment smoothly.
6. Forge.

### Via project JSON (for scripting or hand-editing)

A title-card segment looks like this in a `.forgeproject.json`:

```json
{
  "id": "seg-title-1",
  "type": "segment",
  "video": "C:/Users/bruce/Videos/title_cards/chapter1_1080p.png",
  "still_duration_s": 3.0,
  "audio": {
    "mode": "replace",
    "file": "C:/Users/bruce/Videos/title_cards/chapter1_voice.mp3"
  }
}
```

### A note on transparency

This PNG is transparent, but ForgeAssembler in Phase 1 uses it as the
**base video** of the segment, not as an overlay on top of other footage.
The background of the resulting segment will be black where the PNG is
transparent. If you want the title over moving video behind it, the
right approach in Phase 1 is to design the PNG with a baked-in
background (see the companion doc
[getting_started_black_cutout.md](getting_started_black_cutout.md)) or
place the title on a held frame of the previous clip.

True overlay-on-running-video is a Phase 2 feature.

---

## Step 8 — Export more resolutions

When you're ready to support multiple output sizes:

1. Select your finished frame.
2. Press **Ctrl/Cmd + D** to duplicate it.
3. Click the duplicate and change **W** and **H** in the right sidebar
   to the next resolution (e.g. `3840 × 2160` for `4k`).
4. Re-center the text and adjust the font size so it looks balanced.
5. Export as in Step 6. Save with a clear name — `chapter1_4k.png`.

Repeat for each resolution you plan to forge at.

---

## Troubleshooting

- **Text looks tiny or huge after export.** Your font size didn't scale
  with the frame. Adjust the font size to match the target resolution
  (see Step 4).
- **Exported PNG has a white background.** The frame's fill wasn't
  removed. Go back to Step 3.
- **PNG exports at the wrong pixel size.** Scale wasn't `1x` in the
  Export panel, or the frame's W/H were wrong.
- **Text is fuzzy.** You're viewing it at less than 100%. It will look
  crisp in the video output.
