// Every scene's motion track, laid end to end in OUTPUT time.
//
// This is the viewer's half of what `concat_funscripts` does in the
// engine, and it has to agree with it. A viewer that draws the haptics
// somewhere other than where the forge will write them is worse than no
// viewer: it invites you to approve a seam that does not exist, or miss
// one that does.
//
// ⚠ The rule that matters is the half-open window, and it is not
// cosmetic. A funscript can outlast its own video — one real bundle's
// motion track ran 204ms past what ffmpeg probed — and if those trailing
// actions are carried across a boundary they interleave with the next
// scene's opening ones. Measured on a hard cut, an 18ms/26-unit gap read
// as 1,444 units/s. So an action at exactly the window's end belongs to
// the next scene, never to both.

/**
 * @param {object[]} cues from buildCues
 * @param {Record<string, {actions: {at:number,pos:number}[]}>} bySegId
 *        each scene's own funscript, in SOURCE time
 * @returns {{actions: {at:number,pos:number}[], scenesWithTrack: number,
 *            dropped: number}}
 */
export function mergeSceneActions(cues, bySegId) {
  const actions = [];
  let scenesWithTrack = 0;
  let dropped = 0;

  for (const cue of cues || []) {
    if (cue.kind !== 'scene') continue;          // a hold has no motion
    const src = bySegId?.[cue.segId];
    const list = src?.actions;
    if (!Array.isArray(list) || !list.length) continue;
    scenesWithTrack += 1;

    const winStart = cue.sourceStartMs || 0;
    const winEnd = winStart + (cue.endMs - cue.startMs);
    const offset = cue.startMs - winStart;

    for (const a of list) {
      const at = Number(a?.at);
      if (!Number.isFinite(at)) { dropped += 1; continue; }
      // Half-open: [winStart, winEnd). An action exactly at winEnd is
      // the next scene's first moment, not this one's last.
      if (at < winStart || at >= winEnd) { dropped += 1; continue; }
      actions.push({ at: Math.round(at + offset), pos: Number(a.pos) || 0 });
    }
  }

  // Cues are already in output order and each scene's actions with them,
  // so this is nearly sorted; the sort is here for a source whose own
  // actions arrive out of order rather than for the concatenation.
  actions.sort((x, y) => x.at - y.at);
  return { actions, scenesWithTrack, dropped };
}

/**
 * Peak speed in units/s between consecutive actions, and where it is.
 *
 * The number worth seeing before a forge: a seam that reads as a lurch
 * shows up here as a spike at a scene boundary. Returns null for fewer
 * than two actions.
 */
export function peakSpeed(actions) {
  if (!Array.isArray(actions) || actions.length < 2) return null;
  let best = 0;
  let atMs = 0;
  for (let i = 1; i < actions.length; i += 1) {
    const dt = actions[i].at - actions[i - 1].at;
    if (dt <= 0) continue;               // same instant: not a speed
    const v = (Math.abs(actions[i].pos - actions[i - 1].pos) / dt) * 1000;
    if (v > best) { best = v; atMs = actions[i].at; }
  }
  return { unitsPerS: best, atMs };
}
