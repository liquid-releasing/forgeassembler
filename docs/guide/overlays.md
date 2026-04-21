# Overlays

Overlays are things you drop on top of a section that play across
some or all of it. Three kinds:

- **Image** — a PNG (with alpha) or JPEG, positioned somewhere on
  the frame
- **Audio** — an MP3, WAV, FLAC, or similar, mixed with the section's
  video audio
- **Text** — a string rendered with a system font, any size/colour

Every overlay has timing (start / duration), position (for image and
text), and fade-in / fade-out controls.

## Adding an overlay

1. Build at least one section
2. In the **Add Clips** panel, pick:
   - **OVERLAY on LAST section** — for image or audio (ForgeAssembler
     sniffs the extension)
   - **TEXT on LAST section** — for text
3. Fill in the form that appears
4. Click **Add**

The overlay shows up as a mini-list entry on the section card with a
🖼 / 🎵 / 📝 badge, a short preview, its timing, and a ✕ remove
button.

## Positions (image and text)

Nine named slots arranged in a 3×3 grid:

```
tl    tc    tr
ml  center  mr
bl    bc    br
```

All corner and edge slots use a 5%-of-frame breathing-room margin so
content doesn't sit flush against the edge.

If you need pixel-perfect placement — build a transparent PNG at the
size of your frame with the subject exactly where you want it, then
drop the PNG on at `center`. This keeps the overlay vocabulary small.

## Image overlays

Form fields:

- **File** — path to the PNG/JPG (use 📁 Folder / 📄 File Browse)
- **Position** — one of the nine slots
- **Opacity** — 0–100%
- **Scale %** — overlay width relative to frame width
- **Timing** — start offset into the section, and duration (or "full
  section")
- **Fade in / fade out** — seconds

Transparent PNGs work cleanly — the alpha channel is preserved
through the scale filter.

## Audio overlays

Form fields:

- **File** — path to the audio
- **Mix %** — share of the final blend (0–100%). Replaces the
  Scale slider when the extension is audio.
- **Timing**, **fade in / fade out** — same as image

### Mixing tips

Audio overlays go through `amix` with the section's native audio.
Because `amix` treats every input as equal voltage (not equal
perceived loudness), the inherently-louder source in a mix will
dominate. Two overlays at 50% each will NOT come out balanced if
one was recorded hotter than the other.

Two levers:

- **Hand-tune Mix %** per overlay until the blend sounds right.
  Typical: quiet background music ends up at 40–60%, ambient beds at
  15–25%, and a prominent layer stays at 70–100%.
- **Leave Normalize audio ON** in the sidebar (the default). It
  rebalances levels *across* sections, so an overlay-heavy section
  doesn't come out quieter than a section with strong native audio.
  It does not rebalance inside a single section's mix — that's what
  Mix % is for.

## Text overlays

Form fields:

- **Text** — multi-line input. Newlines render as line breaks.
- **Font** — dropdown of system fonts (scanned from your OS font
  directories)
- **Size** — in pixels, rendered at output resolution
- **Colour** — hex picker
- **Opacity** — 0–100%
- **Position** — one of the nine slots
- **Timing**, **fade in / fade out** — same as image

Notes:

- Apostrophes, colons, URLs, and newlines all render as you'd expect.
  (Under the hood we write the text to a tempfile rather than
  inlining it, so escaping is not your problem.)
- Multi-line text positioned on the right (tr / mr / br) is
  right-aligned; positioned on the left, left-aligned; centred
  slots, centred.
- Font availability is per-machine. If you share a project JSON with
  someone who doesn't have the font, the engine falls back to the
  first installed system font.

---

Next: **[Joiners](joiners.md)** — controlling the transition between
sections.
