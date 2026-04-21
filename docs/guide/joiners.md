# Joiners

A **joiner** is the transition between two sections, or at the very
end of your output. Two types today:

- **Cut** — straight hard cut, no transition
- **Fade to black** — fade out of the previous section, hold on black,
  fade into the next

## Where joiners live in the UI

Every section card has two joiner pickers:

- **Leading joiner** (top) — controls the transition *into* this
  section (from the previous one or, for section 1, from the
  start of the output)
- **Trailing joiner** (bottom) — on non-last sections, edits the
  *next* section's leading joiner. On the last section, edits the
  **closing joiner** — the fade at the very end of your output.

The two pickers are symmetric so you can edit a transition from
either side.

## Fade to black parameters

Two numbers:

- **Hold (s)** — length of the solid-black bridge between sections.
  Adds to the total output duration. Default: 5.0 seconds.
- **Fade (s)** — per-side fade length. Applied *within* the adjacent
  sections. Does NOT add to output duration. Default: 1.0 second.

A typical "film-style" transition looks like:

```
   [section A]                    [section B]
     audio+video                    audio+video
         │   ↘ fade 1s                ↗ fade 1s
         │     ↘                     ↗
         │       ■ ■ ■ ■ ■ hold 5s ■ ■ ■
         │       (solid black)
```

### Just a crossfade (no hold)

Set **Hold = 0** and **Fade > 0**. The engine skips the black bridge
entirely — adjacent sections simply crossfade through black.

### Just a hold (no fade)

Set **Hold > 0** and **Fade = 0**. You'll get a hard cut to black,
the hold duration, then a hard cut back.

### Disable a specific transition

Set the leading (or trailing) joiner dropdown to **Cut**. Both
Hold and Fade inputs hide.

## Closing joiner

The fade at the end of your output. Edit it via the last section's
**trailing** joiner picker. Only the Fade seconds matter for the
closing joiner (there's no section after it to hold before), so the
Hold input is hidden.

Typical: **Fade = 2s** for a gentle film-style ending.

## Colour

Fade-to-black is, unsurprisingly, black by default. Hex colour can
be edited in the project JSON (`leading_joiner.color`) if you want
fade-to-white or fade-to-brand-colour. Not yet exposed in the UI.

## Audio behaviour during fades

The video fade and audio fade are coupled — when the picture fades
out to black, the audio fades in lockstep. When you re-enter on the
far side of the hold, video and audio fade in together. No manual
audio alignment needed.

---

Next: **[Channels](channels.md)** — which funscript channels get
written to the output.
