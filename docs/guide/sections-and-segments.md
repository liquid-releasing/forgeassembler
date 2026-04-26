# Sections & Segments

The ForgeAssembler mental model has three levels. Understanding them
makes everything else in the UI feel obvious.

## The hierarchy

```
Project
├── Output settings (resolution, channels, audio, metadata)
└── Sections (list, top-to-bottom = playback order)
    ├── Section 1
    │   ├── Leading joiner (cut / fade-to-black from previous)
    │   ├── Segments (your clips, played one after another)
    │   └── Overlays (image, audio, text — see Overlays page)
    ├── Section 2
    └── …
```

A **Section** is a logical unit that becomes one chapter in the final
MP4. You name it (the chapter name) and you can drop overlays on it
that span the whole section.

A **Segment** is a single clip within a section. Segments inside a
section cut straight into each other — no transition between them.

## When to start a new section vs extend one

**Start a new section when:**

- The new clip is a different scene, subject, or beat
- You want a chapter boundary for navigation in your player
- You want a fade-to-black separating it from what came before
- You want a different overlay (image, music, title card) on this
  stretch

**Extend an existing section when:**

- The new clip is a continuation of the current scene
- You want the overlays of the current section to keep playing over
  the new clip
- You want no visible transition between the clips

## The five Add Clips modes

The bottom-of-tab **Add Clips** panel offers five modes. They map
directly to the section model:

| Mode | What it does |
|---|---|
| **NEW ONE section** | All added clips become one new section (single chapter) |
| **SEPARATE NEW sections** | Each clip becomes its own section (one chapter per clip) |
| **Into LAST section** | Clips cut straight into the bottom section |
| **OVERLAY on LAST section** | File becomes an image or audio overlay on the last section |
| **TEXT on LAST section** | Opens a text overlay form for the last section |

The first two are the workhorses for building a new project. The
third is how you extend a section. The last two are for overlays.

## Editing a section (focus mode)

Click the **📝** in any section's header to focus on it. The other
sections collapse to one-line summary rows ("Section N · chapter ·
M clips · duration") so you can keep your eye on the one you're
working on. The focused section shows the full controls plus three
extra affordances:

- **⬆ Insert above** — insert a new empty section before this one,
  focus auto-jumps to the new section so you can drop a clip in.
- **⬇ Insert below** — same, but after.
- **Add Clips form (in-card)** — drop a path right inside the
  focused card and it lands in *this* section. Radio modes adapt:
  "Into THIS section (cut-join)", overlay, text. The two NEW-section
  modes are also available if you want to bulk-load from this point.

When you're done, click the orange **Done editing** button at the
bottom of the focused card. All sections expand again.

## Per-segment controls

Each segment card exposes:

- **🔄 Replace** — swap this clip's video file for another via a
  native file picker. Section overlays and joiner stay; funscripts
  auto-rescan against the new file's siblings.
- **✕ Remove** — drop the segment.
- **✂ Split clip at time…** — expand for a small form that splits a
  single video at a timestamp from the source file (see below).
- **Thumbnail + duration + detected funscript channels** — read-only.

Between two consecutive segments inside a section, a small **🔪 Split
here** button appears. Click it to split the section into two at
that boundary — clips below the cut become a new section. Section
overlays redistribute by their time window: anything entirely in the
top half stays; anything entirely in the bottom half moves with
adjusted timing; overlays straddling the boundary split into two.

## ✂ Splitting a clip at a timestamp

For long source videos, you can cut INSIDE a single clip at any
timestamp — no need to pre-split the file with ffmpeg first. The
**✂ Split clip at time…** expander on each video segment lets you
enter a timestamp and the clip becomes two pieces.

The timestamp is **always interpreted as a position in the source
video file**, not relative to where the piece starts in your
project. The expander shows the source file's name and length, plus
the current piece's bounds in source coordinates, so the math stays
obvious as you slice further:

> Source file: `bigvideo.mp4` (01:00:00.000 long)
>
> This piece plays **00:30:00.000 → 01:00:00.000** of the source file.
>
> Split at (timestamp in source file): `00:45:00.000`

When you click **Split here (becomes new section)**:

- The clip becomes two pieces. Both reference the same underlying
  file; the trim window narrows on each side of the cut.
- The second piece **auto-promotes to a new section** (= a new
  chapter in the final MP4).
- Section overlays redistribute the same way as the inter-clip 🔪
  Split here (the two operations share the same engine).

This single feature covers four use cases:

| To do this… | …after the split |
| --- | --- |
| **Multi-chapter** in one long video | Keep both pieces |
| **Trim the start** | Delete the first piece (✕ Remove the first new section) |
| **Trim the end** | Delete the second piece |
| **Mid-video fade-to-black** | Set the new section's leading joiner to fade-to-black |

The timestamps you type **always refer to the original file**, no
matter how many times you split. So you can slice top-down or
bottom-up — same result either way. No mental arithmetic.

## Section naming

Each section has a name input at the top. The name becomes the MP4
chapter title, and it shows in VLC / File Explorer / Plex. Use short,
descriptive names — "Opening card", "Pour sequence", "Closer".

## Chapter markers in the final output

Every section produces one chapter entry in the MP4 container. VLC
briefly overlays the chapter title when you seek into it. If you
leave the section name blank, the chapter falls back to
`Section N`.

---

Next: **[Overlays](overlays.md)** — how to drop an image logo, a
music bed, or a title card on top of a section.
