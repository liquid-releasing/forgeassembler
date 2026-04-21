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

## Reordering

Section cards are top-to-bottom. Drag isn't wired yet — reorder by
editing the project JSON if you need to. The planned **Edit mode**
(see [backlog](https://github.com/liquid-releasing/forgeassembler/issues))
will give you an ✏ button and a move-up/move-down control on each
section.

## Per-segment controls

Each segment card exposes:

- **✂ Split** — cut the clip at a timestamp into two segments
- **✕ Remove** — drop the segment
- **Thumbnail + duration + detected funscript channels** — read-only

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
