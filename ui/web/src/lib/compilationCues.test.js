import { describe, it, expect } from 'vitest';
import { buildCues, cueAt, sourceMsAt, opacityAt, holdBackgroundFrom } from './compilationCues.js';

// Mirrors FA_DATA.joinerAddedMs: only the hold occupies the timeline.
const addedMs = (j) => (j && j.kind !== 'none' ? Math.round((j.holdS || 0) * 1000) : 0);

const FADE = { kind: 'fade_through_black', fadeOutS: 1, holdS: 3, fadeInS: 1 };
const CUT = { kind: 'none' };
const TITLE = {
  kind: 'title_card', text: 'Part Two',
  fadeOutS: 1, holdS: 3, fadeInS: 1,
};

function project(...sections) {
  return { sections };
}
function scene(id, durMs, extra = {}) {
  return { id: `seg-${id}`, file: `${id}.mp4`, durMs, ...extra };
}

describe('buildCues', () => {
  it('puts a joiner BEFORE the scene it introduces', () => {
    // A joiner is a section's LEADING joiner. Getting this backwards
    // would put every scene three seconds early.
    const { cues, totalMs } = buildCues(project(
      { id: 's1', title: 'A', joiner: CUT, segments: [scene('a', 10000)] },
      { id: 's2', title: 'B', joiner: FADE, segments: [scene('b', 10000)] },
    ), addedMs);

    expect(cues.map(c => c.kind)).toEqual(['scene', 'hold', 'scene']);
    expect(cues[0]).toMatchObject({ startMs: 0, endMs: 10000 });
    expect(cues[1]).toMatchObject({ startMs: 10000, endMs: 13000 });
    expect(cues[2]).toMatchObject({ startMs: 13000, endMs: 23000 });
    expect(totalMs).toBe(23000);
  });

  it("opens on the first scene's joiner, which is the compilation's own", () => {
    // The engine lays the first section's leading joiner down at t=0,
    // before any footage, so a title card there is the title for the
    // whole compilation. This used to assert the opposite and the row
    // was hidden in the UI to match, which left an opening title
    // unreachable even though the forge would have rendered it.
    const { cues } = buildCues(project(
      { id: 's1', title: 'A', joiner: FADE, segments: [scene('a', 10000)] },
    ), addedMs);
    expect(cues.map(c => c.kind)).toEqual(['hold', 'scene']);
    expect(cues[0]).toMatchObject({ startMs: 0, endMs: 3000 });
    expect(cues[1]).toMatchObject({ startMs: 3000, endMs: 13000 });
  });

  it('still opens straight on the footage when the first joiner is a cut', () => {
    const { cues } = buildCues(project(
      { id: 's1', title: 'A', joiner: CUT, segments: [scene('a', 10000)] },
    ), addedMs);
    expect(cues.map(c => c.kind)).toEqual(['scene']);
    expect(cues[0].startMs).toBe(0);
  });

  it('counts only the hold, never the fades', () => {
    // The fades are applied inside the neighbouring scenes and add no
    // output time -- 1s + 3s + 1s lengthens the compilation by 3s.
    const { totalMs } = buildCues(project(
      { id: 's1', joiner: CUT, segments: [scene('a', 10000)] },
      { id: 's2', joiner: FADE, segments: [scene('b', 10000)] },
    ), addedMs);
    expect(totalMs).toBe(23000);
  });

  it('honours a trim window', () => {
    const { cues, totalMs } = buildCues(project(
      { id: 's1', joiner: CUT,
        segments: [scene('a', 10000, { trimStartMs: 2000, trimEndMs: 7000 })] },
    ), addedMs);
    expect(totalMs).toBe(5000);
    expect(cues[0].sourceStartMs).toBe(2000);
  });

  it('skips a scene whose duration is not known yet', () => {
    // Otherwise an unprobed scene collapses to zero and every later
    // scene reports the wrong output time.
    const { cues, totalMs } = buildCues(project(
      { id: 's1', joiner: CUT, segments: [scene('a', 0)] },
      { id: 's2', joiner: CUT, segments: [scene('b', 8000)] },
    ), addedMs);
    expect(cues).toHaveLength(1);
    expect(cues[0].file).toBe('b.mp4');
    expect(totalMs).toBe(8000);
  });

  it('a cut produces no hold at all', () => {
    const { cues } = buildCues(project(
      { id: 's1', joiner: CUT, segments: [scene('a', 10000)] },
      { id: 's2', joiner: CUT, segments: [scene('b', 10000)] },
    ), addedMs);
    expect(cues.every(c => c.kind === 'scene')).toBe(true);
  });

  it('carries a title card through as a hold that knows its words', () => {
    const { cues } = buildCues(project(
      { id: 's1', joiner: CUT, segments: [scene('a', 10000)] },
      { id: 's2', joiner: TITLE, segments: [scene('b', 10000)] },
    ), addedMs);
    const hold = cues.find(c => c.kind === 'hold');
    expect(hold.joiner.kind).toBe('title_card');
    expect(hold.joiner.text).toBe('Part Two');
  });

  it('survives an empty project', () => {
    expect(buildCues({ sections: [] }, addedMs)).toEqual({ cues: [], totalMs: 0 });
    expect(buildCues({}, addedMs).totalMs).toBe(0);
  });
});

describe('cueAt', () => {
  const { cues } = buildCues(project(
    { id: 's1', joiner: CUT, segments: [scene('a', 10000)] },
    { id: 's2', joiner: FADE, segments: [scene('b', 10000)] },
  ), addedMs);

  it('finds the cue playing at a moment', () => {
    expect(cueAt(cues, 0).file).toBe('a.mp4');
    expect(cueAt(cues, 9999).file).toBe('a.mp4');
    expect(cueAt(cues, 11000).kind).toBe('hold');
    expect(cueAt(cues, 13000).file).toBe('b.mp4');
  });

  it('treats a boundary as belonging to the cue that starts', () => {
    // Half-open [start, end): at exactly 10000 the first scene is over.
    expect(cueAt(cues, 10000).kind).toBe('hold');
    expect(cueAt(cues, 13000).kind).toBe('scene');
  });

  it('returns null past the end and for an empty list', () => {
    expect(cueAt(cues, 23000)).toBeNull();
    expect(cueAt(cues, 99999)).toBeNull();
    expect(cueAt([], 0)).toBeNull();
  });

  it('clamps a negative time to the start', () => {
    expect(cueAt(cues, -500).file).toBe('a.mp4');
  });
});

describe('sourceMsAt', () => {
  it('maps output time to a timestamp in the source file', () => {
    const { cues } = buildCues(project(
      { id: 's1', joiner: CUT,
        segments: [scene('a', 60000, { trimStartMs: 5000 })] },
    ), addedMs);
    expect(sourceMsAt(cues[0], 0)).toBe(5000);
    expect(sourceMsAt(cues[0], 10000)).toBe(15000);
  });

  it('has no answer for a hold', () => {
    const { cues } = buildCues(project(
      { id: 's1', joiner: CUT, segments: [scene('a', 10000)] },
      { id: 's2', joiner: FADE, segments: [scene('b', 10000)] },
    ), addedMs);
    expect(sourceMsAt(cues[1], 11000)).toBeNull();
  });
});

describe('opacityAt', () => {
  const { cues } = buildCues(project(
    { id: 's1', joiner: CUT, segments: [scene('a', 10000)] },
    { id: 's2', joiner: FADE, segments: [scene('b', 10000)] },
  ), addedMs);
  const first = cues[0];
  const second = cues[2];

  it('dims the tail of the scene before a fade', () => {
    expect(opacityAt(first, 5000)).toBe(1);
    expect(opacityAt(first, 9500)).toBeCloseTo(0.5, 2);
    expect(opacityAt(first, 10000)).toBe(0);
  });

  it('brings the scene after a fade up from black', () => {
    expect(opacityAt(second, 13000)).toBe(0);
    expect(opacityAt(second, 13500)).toBeCloseTo(0.5, 2);
    expect(opacityAt(second, 14000)).toBe(1);
  });

  it('leaves a hold and a hard cut alone', () => {
    expect(opacityAt(cues[1], 11000)).toBe(1);
    const { cues: cutOnly } = buildCues(project(
      { id: 's1', joiner: CUT, segments: [scene('a', 10000)] },
      { id: 's2', joiner: CUT, segments: [scene('b', 10000)] },
    ), addedMs);
    expect(opacityAt(cutOnly[0], 9990)).toBe(1);
  });
});

describe('holdBackgroundFrom', () => {
  const TITLE_PREV = { ...TITLE, background: 'previous_last_frame' };
  const TITLE_NEXT = { ...TITLE, background: 'next_first_frame' };

  function withCard(joiner) {
    return buildCues(project(
      { id: 's1', title: 'A', joiner: CUT,
        segments: [{ ...scene('a', 10000), thumbPath: 'a.png' }] },
      { id: 's2', title: 'B', joiner,
        segments: [{ ...scene('b', 10000), thumbPath: 'b.png' }] },
    ), addedMs);
  }

  it('looks back for the scene before the card', () => {
    const { cues } = withCard(TITLE_PREV);
    const hold = cues.find(c => c.kind === 'hold');
    expect(holdBackgroundFrom(cues, hold).thumbPath).toBe('a.png');
  });

  it('looks forward for the scene after it', () => {
    const { cues } = withCard(TITLE_NEXT);
    const hold = cues.find(c => c.kind === 'hold');
    expect(holdBackgroundFrom(cues, hold).thumbPath).toBe('b.png');
  });

  it('has nothing to show for a flat-colour card or a plain fade', () => {
    const flat = withCard({ ...TITLE, background: 'color' });
    expect(holdBackgroundFrom(flat.cues, flat.cues.find(c => c.kind === 'hold'))).toBeNull();
    const fade = withCard(FADE);
    expect(holdBackgroundFrom(fade.cues, fade.cues.find(c => c.kind === 'hold'))).toBeNull();
  });

  it('returns null for a scene cue or a stray one', () => {
    const { cues } = withCard(TITLE_PREV);
    expect(holdBackgroundFrom(cues, cues[0])).toBeNull();
    expect(holdBackgroundFrom(cues, { kind: 'hold', joiner: TITLE_PREV })).toBeNull();
  });
});

describe('scene cues carry a motion track path', () => {
  it('prefers an explicit map, falls back to a detected one', () => {
    const { cues } = buildCues(project(
      { id: 's1', joiner: CUT,
        segments: [{ ...scene('a', 10000),
                     explicitFunscripts: { main: 'x.funscript' },
                     detectedFunscripts: { main: 'y.funscript' } }] },
      { id: 's2', joiner: CUT,
        segments: [{ ...scene('b', 10000),
                     detectedFunscripts: { main: 'y.funscript' } }] },
      { id: 's3', joiner: CUT, segments: [scene('c', 10000)] },
    ), addedMs);
    expect(cues[0].funscriptPath).toBe('x.funscript');
    expect(cues[1].funscriptPath).toBe('y.funscript');
    expect(cues[2].funscriptPath).toBeNull();
  });
});
