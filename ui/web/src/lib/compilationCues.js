// The compilation as a list of cues: what is on screen at each moment of
// the output, before anything has been forged.
//
// This is what lets the Build tab play the compilation without rendering
// it — scrub to 41:12 and the player knows which source file that is and
// where in it to seek. Nothing else in the app knows that mapping; the
// preview strip colours by speed and the Inspector only ever looks at one
// scene.
//
// It is a pure function on purpose. Getting the timeline wrong by one
// joiner is invisible until you watch the whole thing, which is exactly
// the bug a test catches for free — and nothing in this suite mounts a
// component, so it could not be tested inside the player.

import { effectiveDurMs } from './projectAdapter';

/**
 * Cues in output order.
 *
 * ⚠ A joiner is a section's LEADING joiner — the transition INTO it — so
 * it comes before that section's scenes, never after. `projectDurationMs`
 * adds the two in the opposite order, which is harmless when you are only
 * summing but would put every scene in the wrong place here.
 *
 * The first section never gets one: there is nothing before it to
 * transition from. That mirrors the engine, and it is the invariant the
 * canvas relies on.
 *
 * Only the hold occupies the timeline. The fades live inside the
 * neighbouring scenes and add no output time, so they are carried on the
 * scene cues as `fadeOutMs` / `fadeInMs` for the player to dim with,
 * rather than becoming cues of their own.
 *
 * @param {object} project view-model project
 * @param {(j: object) => number} joinerAddedMs FA_DATA.joinerAddedMs
 * @returns {{cues: object[], totalMs: number}}
 */
export function buildCues(project, joinerAddedMs) {
  const cues = [];
  let t = 0;
  const sections = project?.sections || [];

  // The compilation's own title page, before any section.
  const opening = project?.output?.openingJoiner;
  const openingMs = opening && joinerAddedMs ? joinerAddedMs(opening) : 0;
  if (openingMs > 0) {
    cues.push({
      kind: 'hold', startMs: 0, endMs: openingMs,
      sectionId: null, joiner: opening,
    });
    t += openingMs;
  }

  sections.forEach((sec) => {
    // The first section's joiner counts too — it is the compilation's
    // opening card, and the engine lays it down before any footage.
    const joiner = sec.joiner;
    const holdMs = joiner && joinerAddedMs ? joinerAddedMs(joiner) : 0;
    if (holdMs > 0) {
      cues.push({
        kind: 'hold',
        startMs: t,
        endMs: t + holdMs,
        sectionId: sec.id,
        joiner,
      });
      t += holdMs;
    }

    const fadeInMs = joiner && joiner.kind !== 'none'
      ? Math.round((joiner.fadeInS || 0) * 1000) : 0;
    // The fade-out belongs to the LAST scene before the NEXT joiner, so
    // it is filled in on the way past, below.
    for (const seg of sec.segments || []) {
      const d = effectiveDurMs(seg);
      // A scene whose duration is not known yet (not probed, or a
      // missing file) would otherwise collapse the timeline and put
      // every later scene at the wrong time. Skip it and say so.
      if (!(d > 0)) continue;
      cues.push({
        kind: 'scene',
        startMs: t,
        endMs: t + d,
        sectionId: sec.id,
        segId: seg.id,
        file: seg.file,
        title: sec.title || seg.title || '',
        // Where in the SOURCE this cue starts. Output time minus this
        // cue's start, plus the trim-in, is the source timestamp.
        sourceStartMs: seg.trimStartMs || 0,
        // Carried so a title card backed by a neighbouring frame has
        // something to show before anything is forged.
        thumb: seg.thumb || null,
        thumbPath: seg.thumbPath || null,
        // The scene's motion track, so the viewer can draw the haptics
        // across the whole compilation. `main` is the bare .funscript
        // every station falls back to; a `.forge` import carries an
        // explicit map, a detected folder a discovered one.
        funscriptPath: (seg.explicitFunscripts || {}).main
                      || (seg.detectedFunscripts || {}).main
                      || null,
        fadeInMs: cues.length && fadeInMs ? fadeInMs : 0,
        fadeOutMs: 0,
      });
      t += d;
    }
  });

  // Walk back over the scene cues and hand each the fade-out of the
  // joiner that follows it, so the player can dim the tail of a scene
  // the way the render will.
  for (let i = 0; i < cues.length; i += 1) {
    if (cues[i].kind !== 'hold') continue;
    const j = cues[i].joiner;
    const fadeOutMs = j && j.kind !== 'none'
      ? Math.round((j.fadeOutS || 0) * 1000) : 0;
    for (let k = i - 1; k >= 0; k -= 1) {
      if (cues[k].kind === 'scene') { cues[k].fadeOutMs = fadeOutMs; break; }
    }
  }

  return { cues, totalMs: t };
}

/**
 * The cue playing at `ms`, or null when the compilation is empty or `ms`
 * is past the end. Cues are contiguous and half-open — [startMs, endMs) —
 * so a boundary belongs to the cue that is starting, never to both.
 */
export function cueAt(cues, ms) {
  if (!cues || !cues.length) return null;
  const t = Math.max(0, ms);
  // Binary search: a sixteen-scene compilation is small, but this runs on
  // every timeupdate.
  let lo = 0;
  let hi = cues.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (t < cues[mid].startMs) hi = mid - 1;
    else if (t >= cues[mid].endMs) lo = mid + 1;
    else return cues[mid];
  }
  return null;
}

/**
 * Where in the source file a scene cue is at output time `ms`.
 * Returns null for a hold, which has no source.
 */
export function sourceMsAt(cue, ms) {
  if (!cue || cue.kind !== 'scene') return null;
  return (cue.sourceStartMs || 0) + (Math.max(cue.startMs, ms) - cue.startMs);
}

/**
 * How much to dim a scene cue at output time `ms`, as an opacity 0..1,
 * from the fades of the joiners either side of it.
 */
export function opacityAt(cue, ms) {
  if (!cue) return 1;
  if (cue.kind === 'hold') return 1;
  const intoCue = ms - cue.startMs;
  const left = cue.endMs - ms;
  if (cue.fadeInMs > 0 && intoCue < cue.fadeInMs) {
    return Math.max(0, Math.min(1, intoCue / cue.fadeInMs));
  }
  if (cue.fadeOutMs > 0 && left < cue.fadeOutMs) {
    return Math.max(0, Math.min(1, left / cue.fadeOutMs));
  }
  return 1;
}

/**
 * The scene a title card borrows its background from, or null.
 *
 * ⚠ This is the neighbouring scene, not the exact frame the forge will
 * use. The render searches backwards (or forwards) for the last non-blank
 * frame, because scenes routinely end on black; the preview only has the
 * scene's thumbnail. So it answers "which scene is behind the card",
 * which is the part worth checking before a twenty-minute encode.
 */
export function holdBackgroundFrom(cues, holdCue) {
  if (!holdCue || holdCue.kind !== 'hold') return null;
  const bg = holdCue.joiner?.background;
  if (bg !== 'previous_last_frame' && bg !== 'next_first_frame') return null;
  const i = cues.indexOf(holdCue);
  if (i < 0) return null;
  const step = bg === 'previous_last_frame' ? -1 : 1;
  for (let k = i + step; k >= 0 && k < cues.length; k += step) {
    if (cues[k].kind === 'scene') return cues[k];
  }
  return null;
}
