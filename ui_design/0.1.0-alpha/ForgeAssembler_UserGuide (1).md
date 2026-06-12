# ForgeAssembler — User Guide

> **alpha 0.2 · pre-release software**

ForgeAssembler turns a folder of short haptic videos into one long one — with chosen transitions, a continuous audio layer that survives every cut, optional title cards, drag-to-reorder clips, and every funscript channel concatenated in lockstep. This guide walks the desktop UI tab-by-tab and explains the pieces that don't appear in any video editor: **joiners**, **audio beds**, and **funscript channel coverage**.

**One pass, four steps:** `Project → Build → Output → Forge` · plus a Joiners library for transitions, and a Tweaks panel for layout preferences.

---

## Contents

**Orientation**
- [What ForgeAssembler does](#what-forgeassembler-does)
- [The interface at a glance](#the-interface-at-a-glance)
- [Sections, segments, joiners](#sections-segments-joiners)

**Pipeline**
- [01 · Project](#01--project)
- [02 · Build](#02--build)
- [03 · Output](#03--output)
- [04 · Forge](#04--forge)

**Deep dives**
- [Joiners (transitions)](#joiners-transitions)
- [Audio beds (cross-clip audio)](#audio-beds-cross-clip-audio)
- [Title cards & overlays](#title-cards--overlays)
- [Trim window editor](#trim-window-editor)
- [Multi-select bulk operations](#multi-select-bulk-operations)
- [Drag & drop reference](#drag--drop-reference)
- [Funscript channel handling](#funscript-channel-handling)
- [Saving and opening projects](#saving-and-opening-projects)

**Reference**
- [Tweaks panel](#tweaks-panel)
- [Glossary](#glossary)

---

## What ForgeAssembler does

ForgeAssembler is a local desktop tool — Windows, macOS, Linux. No account, no cloud, no telemetry. Pre-release software.

You give it a list of short videos and their adjacent funscripts; it gives you back one combined video plus one combined funscript per channel, with chapter markers at every section boundary and a reusable `.forgeproject.json` sidecar.

It is **not a video editor**. There's no per-clip compositing, no colour grading beyond a single temperature nudge per clip. Author your clips in FunscriptForge (or elsewhere), then point ForgeAssembler at the folder.

---

## The interface at a glance

The pipeline runs left-to-right:

```
┌──────────┬────────┬────────┬───────┐  │  ┌──────────┐
│ 01       │ 02     │ 03     │ 04    │  │  │ Joiners  │
│ Project ●│ Build  │ Output │ Forge │  │  │ library  │
└──────────┴────────┴────────┴───────┘  │  └──────────┘
                    pipeline tabs       │  utility tab
```

Each step writes a chain file the next step reads. A green dot on a tab means **Accepted** — locked in for downstream tabs. Tabs whose upstream isn't accepted dim slightly to signal "you can visit, but the work upstream isn't ready yet." You can move backwards at any time; re-accepting an earlier step propagates forward.

- **Top bar** — project name, save status (unsaved · unsaved changes · saved · saved 2 min ago), total duration, segment count, resolution. Open / Save / Undo / Redo buttons.
- **Status bar** — sync state, current tab, chain file written, ffmpeg version, app version.

---

## Sections, segments, joiners

ForgeAssembler's data model has three nouns. Learning them once unlocks everything else.

- **Segment** — one clip in the timeline. A video file, a still image (PNG title card), or in the future a generated card. Every segment has a duration, an audio mode (`keep` · `replace` · `silence`), optional overlays, an optional colour temperature offset, and the funscript channels detected next to it.
- **Section** — a named group of segments. Sections become **chapters** in the output MP4. Inside a section, segments are joined with straight cuts. Between sections you choose the transition.
- **Joiner** — a transition. Each section has a *leading joiner* that describes how it transitions in from the previous section. The first section's joiner is always `cut`.

There's a fourth concept that doesn't fit in those three: **audio beds**. A bed is a continuous audio layer that spans multiple clips, riding over the per-clip audio. See [Audio beds](#audio-beds-cross-clip-audio).

---

## 01 · Project

> Where you name the output and decide what gets produced.

Three controls matter here:

- **Basename** & **Output folder** — where the bundle lands. Everything ForgeAssembler writes is prefixed with the basename, in this folder.
- **Produce** toggles — Video MP4, Funscripts, Haptic-estim audio, and the loudness normalise switch. *Chapter markers are always written when video is produced.*
- **Recents** — a list of recent `.forgeproject.json` files. Click to reopen.

> 💡 **Tip.** A project can produce video without funscripts, or funscripts without video. If you've already cut the video elsewhere and only need the combined haptic bundle, turn the video toggle off — ForgeAssembler skips the whole ffmpeg video pipeline.

---

## 02 · Build

> The main surface. Add clips, arrange them into sections, pick the transitions, lay down audio beds.

### Stats strip

Top of the canvas: `Total duration · Sections · Segments · Audio beds · Resolution`. Updates live as you change the project.

### Clip rows

Each row shows: drag handle, section colour stripe, thumbnail (with duration badge and a `STILL` flag for still-image segments), title and filename, audio mode, the funscript channels detected for this clip, and a row of icon actions (split, duplicate, remove).

```
≡ │ [thumb 3:04] │ Cut 05 · tease            │ 🔊 keep │ main · m-ax · estim │ ✂ ⎘ 🗑
  │              │ act2_01.mp4                │         │                     │
```

**Click a clip to select it.** The right inspector opens with five tabs: Source · Audio · Overlays · Color · Funscript.

**Shift-click another clip** to extend the selection through a range; **⌘ / Ctrl-click** to toggle individual clips in or out. With multiple clips selected, the right inspector switches to bulk-edit mode — see [Multi-select](#multi-select-bulk-operations).

### Section headers

Each header carries a colour swatch, an index (`02 / 04`), a **clickable name** (rename in place — Enter to commit, Esc to cancel), a chapter pill, a clip-count chip, and two add buttons: **Title card** and **Add clip**.

```
≡  ▣  02 / 04   Chapter 1 · Build   🔖 ch.02 @ 0:51   ⟨2 clips⟩       + Title card  + Add clip  ⋯
```

The orange **🔖 ch.02 @ 0:51** pill makes it explicit that this section becomes chapter 2 in the output MP4, starting at 0:51. The name you type here is the chapter title that gets written.

The grip handle on the left of the header drags the whole section to reorder; its leading joiner moves with it.

### Joiner pills

Between sections you'll see one of three visual treatments (set by the `Joiner style` tweak; default is the inline pill):

```
─────────────  ◉ fade through black · 2.5s  ▾  ─────────────
```

Click any pill to open the [joiner editor](#joiners-transitions). Inside a section (between two clips in the same group) the joiner is always `cut` and isn't editable.

### Audio bed lane

A single horizontal lane below the clip list. See [Audio beds](#audio-beds-cross-clip-audio).

### Live preview band

Sticky at the bottom, above the Accept/Forge bar. Renders a heatmap of the combined funscript's velocity by colour, peak markers on the beatmap below, total duration, action count, average BPM, peak velocity, and which channels are active. Hover for a timecode at any point in the timeline. No rendering needed — it's all computed in-process from your project.

---

## Joiners (transitions)

> A joiner is one transition with up to three timing values. You don't pick "fade out" and "fade in" separately — they're the same joiner.

### The editor

Click any joiner pill to open the editor in place. Five built-in kinds:

| Kind | What it does | Parameters |
|---|---|---|
| **Cut** | Straight cut. Previous frame ends, next frame begins. | — |
| **Fade through black** | One transition with three parts: previous clip fades out, holds black, next clip fades in. | `fade out · hold · fade in · color` |
| **Crossfade** | Dissolves from previous to next. Clips overlap. | `duration · easing` |
| **Dip to color** | Like fade through black, but you pick the hold colour. | `fade out · hold · fade in · color` |
| **Swipe** | Soft-edged wipe pushing the next clip in from one edge. | `duration · direction · easing · softness` |

### Animated preview

At the top of the editor: a 16:9 frame that **plays the transition on loop**. The two panels are the previous clip's last frame and the next clip's first frame. Play / pause / restart controls + a mini scrubber show the playhead riding through the transition window. Adjust any parameter and the preview reflects it immediately — useful for dialling in fade timings without forging.

### The timing visualisation

For fade-style joiners the editor also shows a static proportional bar of the three timing values, with the hold colour painted in the middle and gradients on either side:

```
[░░░░░░░░░░ fade out 2.5s ░░░░░░░░░░│■ hold 0.5s ■│░░░░░░░░░░ fade in 2.5s ░░░░░░░░░░]
```

This is the answer to "where is the fade-from-black control?" — there's only one joiner, with three timing values. The middle bar is the hold-at-black duration; set it to zero for a classic no-hold fade.

### User joiners (custom presets)

Save any joiner configuration as a named preset. From the editor: **Save as preset…** → name it → it appears under *Your joiners* in the inline picker forever after.

The full library lives on the **Joiners** tab (utility, right side of the tab strip):

- **Built-in kinds** with their defaults — and a *Create preset from this* button on each.
- **Your joiners** — every preset, editable and removable.
- **+ New joiner** top-right — full authoring modal: pick a built-on kind, name it, tune the params, save.

> 💡 **When to make a preset.** Anytime you find yourself dialling in the same fade values across multiple section boundaries. The presets are project-scoped; they live in your `.forgeproject.json` alongside the section list.

---

## Audio beds (cross-clip audio)

> A continuous audio layer that survives joiners.

Without beds, every clip carries its own audio that cuts hard at every joiner — fine for hard cuts but jarring across a fade. A **bed** is one audio file you place across a range of clips. It rides over the per-clip audio and crossfades over the joiners in between, so the music or ambience doesn't break.

```
─────┬─────────┬─────────┬─────────┬─────  ← clip boundaries
     │░░░ Hypnotic tech house · −18dB · in 2s · out 4s · duck ░░░│
─────┴─────────┴─────────┴─────────┴─────
```

### Bed properties

- **Coverage** — start segment, end segment.
- **Level** — dB offset (default −18dB; gentler when ducking).
- **Fade in** & **fade out** — at the bed's own edges.
- **Behaviour vs clip audio** — *Duck under clips* (clip audio drops to −12 dB while the bed plays) or *Replace clips* (per-clip audio muted under coverage).

### Editing a bed

Click any bed in the lane → the right inspector switches from clip mode to bed mode, with the properties above. Click an empty area of the lane or use *+ Add bed* to start a new one.

---

## Title cards & overlays

> Author titles directly in ForgeAssembler. Two output paths: a standalone segment, or an overlay on an existing clip.

### Opening the editor

- **Build header** → *New title card*. Opens with the currently-selected clip as the anchor (if any).
- **Section header** → *Title card*. Opens scoped to that section.
- **Inspector → Overlays tab** → *Title overlay*. Pre-targets the selected clip in overlay mode.

### Templates row

A scrollable strip at the top of the editor shows the **4 built-in layouts** as thumbnail previews plus any **user-saved templates** (with a "saved" badge). Click any card to load its layout / theme / glyph / position into the current draft. Body text isn't loaded from a template — only the styling.

The footer's **Save as template…** button names the current styling and adds it to the project's `userTitleTemplates` for reuse.

### Use as: Standalone segment

The new title becomes its own still-image segment. Three insertion-point choices when a clip is selected: *Before clip · After clip · End of section*. Hold-on-screen duration is yours to set (1–15s).

### Use as: Overlay on a clip

The editor pivots: the preview composites the title over the selected clip's thumbnail at the chosen position, and the right rail swaps to overlay-specific controls:

- **Position on clip** — a 3×3 grid: `top-left · top-center · top-right · middle-left · center · middle-right · bottom-left · bottom-center · bottom-right`. Each layout has a default cell (marked with a warm-orange dot — *Centered hero* → center, *Chapter plate* → middle-left, *Lower third* → bottom-left, *Full quote* → center). Override to any of the 9.
- **Start at** — when in the clip the overlay appears.
- **Fade in** & **fade out** — overlay edges.
- **Opacity** — 20%–100%.

The output is a transparent-background PNG registered on the clip's overlay list.

### Glyph picker

Replaces the old "show anvil" toggle. Seven built-in glyphs:

| Glyph | Use |
|---|---|
| **None** | No glyph |
| **Anvil** | Default — the brand mark |
| **Hammer** | Tool theme |
| **Tongs** | Tool theme |
| **Oven** | Forge theme |
| **Spark** | Accent glyph for transitions |
| **Dot** | Minimal punctuation |

Plus a dashed **+ custom** tile that opens a file picker. Drop in any **SVG** (sharpest) or **PNG**; it's stored as a data URI in the project's `userGlyphs` list and shown in the picker forever after with a small "custom" tag.

### Layouts

| Layout | Best for | Behaves like |
|---|---|---|
| **Centered hero** | Openings, name plates. | Big centred type, optional glyph above. |
| **Chapter plate** | Act / chapter markers. | Eyebrow + title + subtitle, left-aligned with accent bar. |
| **Lower third** | Persistent labels over video. | Bottom-left text with a legibility scrim. Good for overlay mode. |
| **Full quote** | Statements, dedications. | Type fills the frame; optional attribution below. |

### Themes

Four themes — **Dark**, **Void**, **Brand**, **Light** — set the background, foreground, and accent colours. In overlay mode the background is replaced by your video; only the type, accent stripes, and (for lower-third / full quote) the legibility scrim are baked into the PNG.

---

## Trim window editor

> The Inspector → Source pane shows a visual scrubber with draggable in/out handles for every video clip.

```
in 00:25.40                          used 2:25.6                          out 02:50.10

┌────────────────────────────────────────────────────────────────────┐
│░░░░░░░░░│■   ◆──────────── trim window ────────────◆   ■│░░░░░░░░░│
└────────────────────────────────────────────────────────────────────┘
0:00.00         source duration · 03:15.00                     03:15.00
```

- **Numeric strip on top**: `in 00:25.40 · used 2:25.6 · out 02:50.10`
- **Draggable handles** (warm-orange bars with circular grab dots). The handle being dragged turns accent-red, with a tooltip above showing live timecode.
- **Dimmed dark regions** on either side = cut from the source.
- **Warm-tinted band in the middle** = the selected trim window (a faint thumb-strip pattern behind hints at the source content).
- **Playhead** as a thin white stripe rides through as the MediaViewer plays.
- Click anywhere on the track (outside handles) to scrub the playhead.
- Handles can't cross; a 200ms minimum window is enforced.

The MediaViewer above the scrubber binds its chapter to the trim window, so its baton position reflects where in the trimmed range playback is.

Stills don't get a trim scrubber — they get a duration slider instead.

---

## Multi-select bulk operations

> Select many clips. Edit common values once. The Inspector switches to a bulk view.

### Selection

- **Click** — replaces selection (one clip)
- **Shift-click** — selects the range from the anchor (last single-clicked clip) through the clicked one, across sections
- **⌘ / Ctrl-click** — toggles a clip in / out of the current selection
- **Esc** — clears

All selected clips show the same accent border + tinted background.

### Bulk inspector

When N > 1 clips are selected, the right inspector replaces the per-clip tabs with a bulk view:

- **Header** — count badge, total duration, kind mix ("3 videos · 1 still"), close ⓧ
- **Thumbnail pile** of up to 9 clips with a +N overflow
- **Quick actions** — Duplicate · Split… · Remove
- **Audio mode** segmented (Keep / Replace / Silence). If all selected clips share a value, it's active; if mixed, nothing's active and the strip below shows the distribution ("currently: keep (2) · silence (1)"). Click any option to apply to all.
- **Color temperature** — slider + an *Apply +200K to N clips* button. If the selection includes any stills, this section is replaced with an explanation that temperature is video-only.
- **Funscript channels** — coverage rows: green check + count when all selected clips have it; amber alert when partial (`2 / 4`).
- **Overlay** — bulk overlay is marked "coming soon" — overlay timing benefits from per-clip review.

---

## Drag & drop reference

All reordering on Build uses the grip handles, never the row body. Two scopes:

| Drag | Drop on | Result |
|---|---|---|
| Clip's ≡ handle | Another clip, before half | Insert before that clip (within or across sections). |
| Clip's ≡ handle | Another clip, after half | Insert after that clip. |
| Section's ≡ handle | Another section header | Reorder whole section (its joiner travels with it). |

During a drag the source row dims to 40% opacity. An accent stripe marks the drop slot. Press `Esc` to cancel.

> **Edge case:** if a section is empty (no clips), dropping a clip into it isn't currently supported via drag — use the section header's *Add clip* button or move clips one at a time.

---

## 03 · Output

> Resolution, quality, audio normalisation, bug overlay — and how to handle funscript channel gaps.

### Resolution

Choose from:

- **16:9** — 1080p (1920×1080) · 1440p (2560×1440) · 4K (3840×2160)
- **21:9 ultrawide** — UW 1080p (2560×1080) · UW 1440p (3440×1440)
- **4:3** — 4:3 HD (1440×1080)
- **Vertical** — 3:4 HD (1080×1440) · 9:16 HD (1080×1920)
- **Source** — copy the first clip's resolution at forge time

Aspect ratio is preserved — narrower clips get pillarboxed, taller clips get letterboxed.

### Quality & frame rate

Quality preset maps to an H.264 CRF: `Low · CRF 28`, `Medium · CRF 23` (default), `High · CRF 18`. Frame rate: `Source · 24 · 30 · 60`. Picking *Source* probes the first clip with ffprobe and matches.

### Audio

- **Normalize audio loudness** — single-pass `loudnorm` at −16 LUFS (YouTube reference) over the combined audio.
- **Haptic-estim audio (WAV)** — toggles concatenation of `.stereostim.wav` channels in lockstep.

### Bug overlay

A small PNG (with transparency) that rides every segment in a chosen corner with a chosen opacity and pixel margin. Classic network-logo bug. One PNG, four corner choices, opacity slider.

---

## Funscript channel handling

Funscript channels aren't opt-in — ForgeAssembler detects them automatically by scanning the folder beside each clip. The **Output channels** card lists every variant that exists somewhere in your project, with a coverage bar:

| State | What you see |
|---|---|
| **Continuous** | Full coverage — every eligible clip has this channel. No gaps to resolve. |
| **Partial** | Some clips have it, others don't. You pick a gap policy. |

### Gap-policy choices

For each partially-covered channel:

- **Blank** (default for funscripts) — hold the last position; no new actions during the gap.
- **Basic** — synthesise basic motion from the main channel as a fallback.
- For `audio_estim`: **Silence** or **Tone** (low-level guide tone derived from the main channel).

Channels not detected anywhere in the project collapse into a footer "*N channels not detected*" disclosure — they're not in the output, no decision needed.

---

## Saving and opening projects

> The TopBar shows save status next to the project name and routes you through the right dialogs.

### Status indicator

The pill next to the filename communicates state:

| Pill | Meaning |
|---|---|
| **unsaved** (warm) | Project has no path yet — first save will open Save As. |
| **unsaved changes** (amber) | Has a saved path but edits since last save. |
| **saved** (green) | Fully synced; subtitle shows "saved just now / 2 min ago / 1h ago". |

The Save button adapts: **Save as…** (no path) → **Save changes** (dirty, primary-styled) → **Saved** (clean, secondary).

### Save As dialog

Opens on first save or when explicitly invoked:

- **File name** — slugged into `<basename>.forgeproject.json`.
- **Folder** — text field + Browse button.
- **What gets written now** — callout showing the path that will be written.

A reminder that the project file is a small JSON sidecar; video / funscript outputs are written later when you press **Forge**.

### Open Project dialog

Two paths:

- **Browse for a file…** — opens the OS file picker (only `.forgeproject.json` files shown).
- **Recent projects** — a list of recently-opened projects with path, modified time, clip count, duration. Click to open.

### Unsaved changes prompt

If you click Open while the current project has unsaved changes, an intercept dialog asks: **Cancel · Don't save · Save and continue**. *Save and continue* routes through the Save As dialog if there's no path yet, otherwise saves in place then opens the Open dialog.

---

## 04 · Forge

> One pass. ForgeAssembler concatenates the videos, the funscript channels in lockstep, the audio, and writes chapter markers for every section boundary.

### Summary card

Sections · segments · audio beds · total duration · resolution · loudness · channels — a one-glance recap before you commit.

### Outputs that will be written

A live list of files. Multi-axis funscripts indent under their main; the `.forgeproject.json` sidecar is always last:

- `basename.mp4` — combined video
- `basename.funscript` — main
- `basename.pitch.funscript · roll · surge · …`
- `basename.alpha.funscript · beta`
- `basename.alt.funscript` — alternate funscripts
- `basename.stereostim.wav` — haptic-estim audio
- `basename.forgeproject.json` — reusable project sidecar

### Chapter markers card

Every section becomes a chapter in the output. The Chapter markers card lists them explicitly before you forge:

| ch. | Time | Title | Duration | Clips |
|----|-------|--------|----------|-------|
| ch.01 | 0:00 | Opening | 12.4s | 2 clips |
| ch.02 | 0:51 | Chapter 1 · Build | 7:51 | 3 clips |
| ch.03 | 9:02 | Chapter 2 · Crest | 1:32 | 3 clips |

The section names you typed on Build are the chapter titles that get written. Footer reads:
*"written to `basename.mp4` as MOV/MP4 chapter atoms · also embedded in `basename.funscript` metadata."*

Timecodes account for joiner durations — a fade-through-black with 2.5s out + 0.5s hold + 2.5s in adds 5.5s before the next chapter starts.

### The Forge button

A single primary CTA on a quiet brand-gradient panel. Pressing it kicks the ffmpeg passes — progress and ETA appear below the button. Don't close the app while a forge is running; outputs appear in your project folder as each step completes.

---

## Tweaks panel

The Tweaks toggle in the toolbar opens a floating panel with personal layout preferences. They persist across sessions:

| Tweak | Options |
|---|---|
| **Build layout** | Sections · Flat · Timeline |
| **Density** | Compact · Comfy · Roomy |
| **Section grouping** | On / off (off collapses to flat) |
| **Joiner style** | Inline pill · Divider · Lane |
| **Inspector** | Right panel · Inline (expands the clip row) |
| **Sample project** | S (4 clips) · M (8) · L (14) |

---

## Glossary

| Term | Meaning |
|---|---|
| **Segment** | One clip in the timeline. Video file or still image. |
| **Section** | Named group of segments. Becomes a chapter in the output. |
| **Joiner** | Transition between two sections. Includes timing values. |
| **Audio bed** | Continuous audio layer that spans many segments and crossfades over joiners. |
| **Overlay** | Image (or title PNG) layered onto a segment, with start time, fade, opacity, position. |
| **Bug** | Persistent corner-PNG overlay applied to every segment. Project-level. |
| **Glyph** | A small brand mark drawn into title cards. Anvil is the default; users can upload SVGs / PNGs. |
| **Template** | A saved title-card styling (layout + theme + glyph + position). Project-scoped. |
| **Trim window** | The portion of a source video that contributes to the timeline. Set with the visual scrubber. |
| **Chain file** | The output of one pipeline step that the next step reads. |
| **Forge** | The final pass — running ffmpeg and the funscript concat to write the bundle. |
| **Channel** | One funscript variant: main, pitch, roll, alpha, beta, alt, audio-estim, etc. |
| **Gap policy** | Per-channel rule for what to do when a clip lacks that channel. Blank / Basic / Silence / Tone. |
| **Dirty** | State of having unsaved changes. Shown as an amber pill in the TopBar. |

---

*ForgeAssembler v0.2.0-alpha · ForgeAssembler™ and Liquid Releasing™ are trademarks of Liquid Releasing · MIT-licensed source. Pre-release software, provided as-is. Runs entirely on your machine — no account, no cloud, no telemetry.*
