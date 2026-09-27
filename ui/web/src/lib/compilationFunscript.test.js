import { describe, it, expect } from 'vitest';
import { buildCues } from './compilationCues.js';
import { mergeSceneActions, peakSpeed } from './compilationFunscript.js';

const addedMs = (j) => (j && j.kind !== 'none' ? Math.round((j.holdS || 0) * 1000) : 0);
const CUT = { kind: 'none' };
const FADE = { kind: 'fade_through_black', fadeOutS: 1, holdS: 3, fadeInS: 1 };

function twoScenes(joiner, segExtra = {}) {
  return buildCues({
    sections: [
      { id: 's1', joiner: CUT,
        segments: [{ id: 'seg-a', file: 'a.mp4', durMs: 10000, ...segExtra }] },
      { id: 's2', joiner,
        segments: [{ id: 'seg-b', file: 'b.mp4', durMs: 10000 }] },
    ],
  }, addedMs).cues;
}

describe('mergeSceneActions', () => {
  it('lays each scene after the one before it', () => {
    const cues = twoScenes(CUT);
    const { actions } = mergeSceneActions(cues, {
      'seg-a': { actions: [{ at: 0, pos: 0 }, { at: 5000, pos: 100 }] },
      'seg-b': { actions: [{ at: 0, pos: 50 }, { at: 5000, pos: 10 }] },
    });
    expect(actions.map(a => a.at)).toEqual([0, 5000, 10000, 15000]);
  });

  it('leaves a gap for the hold, which has no motion', () => {
    const cues = twoScenes(FADE);        // 10s + 3s hold + 10s
    const { actions } = mergeSceneActions(cues, {
      'seg-a': { actions: [{ at: 9000, pos: 0 }] },
      'seg-b': { actions: [{ at: 0, pos: 100 }] },
    });
    expect(actions.map(a => a.at)).toEqual([9000, 13000]);
  });

  it('DROPS a funscript that outlasts its own video', () => {
    // The seam bug, in the viewer. One real bundle's track ran 204ms past
    // the video; carried across a cut it interleaved with the next
    // scene's opening actions and read as 1,444 units/s.
    const cues = twoScenes(CUT);
    const { actions, dropped } = mergeSceneActions(cues, {
      'seg-a': { actions: [{ at: 9900, pos: 40 }, { at: 10204, pos: 66 }] },
      'seg-b': { actions: [{ at: 0, pos: 34 }] },
    });
    expect(actions.map(a => a.at)).toEqual([9900, 10000]);
    expect(dropped).toBe(1);
  });

  it('treats the window as half-open, so a boundary action is not doubled', () => {
    const cues = twoScenes(CUT);
    const { actions } = mergeSceneActions(cues, {
      'seg-a': { actions: [{ at: 10000, pos: 99 }] },   // exactly at the end
      'seg-b': { actions: [{ at: 0, pos: 1 }] },
    });
    // The action at exactly 10000 belongs to the next scene's first
    // moment, so scene A contributes nothing.
    expect(actions).toEqual([{ at: 10000, pos: 1 }]);
  });

  it('honours a trim window at both ends', () => {
    const cues = twoScenes(CUT, { trimStartMs: 2000, trimEndMs: 7000 });
    const { actions, dropped } = mergeSceneActions(cues, {
      'seg-a': {
        actions: [
          { at: 1000, pos: 10 },   // before the trim-in: gone
          { at: 2000, pos: 20 },   // the new zero
          { at: 6999, pos: 30 },
          { at: 7000, pos: 40 },   // at the trim-out: gone
          { at: 9000, pos: 50 },   // after: gone
        ],
      },
    });
    expect(actions).toEqual([{ at: 0, pos: 20 }, { at: 4999, pos: 30 }]);
    expect(dropped).toBe(3);
  });

  it('skips scenes with no track and counts the ones that have one', () => {
    const cues = twoScenes(CUT);
    const r = mergeSceneActions(cues, { 'seg-a': { actions: [{ at: 0, pos: 0 }] } });
    expect(r.scenesWithTrack).toBe(1);
    expect(r.actions).toHaveLength(1);
  });

  it('survives nothing at all', () => {
    expect(mergeSceneActions([], {}).actions).toEqual([]);
    expect(mergeSceneActions(null, null).actions).toEqual([]);
    const cues = twoScenes(CUT);
    expect(mergeSceneActions(cues, { 'seg-a': { actions: 'nope' } }).actions).toEqual([]);
  });

  it('drops a malformed timestamp rather than emitting NaN', () => {
    const cues = twoScenes(CUT);
    const { actions, dropped } = mergeSceneActions(cues, {
      'seg-a': { actions: [{ at: 'x', pos: 1 }, { at: 500, pos: 2 }] },
    });
    expect(actions).toEqual([{ at: 500, pos: 2 }]);
    expect(dropped).toBe(1);
  });
});

describe('peakSpeed', () => {
  it('finds the fastest move and says where', () => {
    const r = peakSpeed([
      { at: 0, pos: 0 }, { at: 1000, pos: 10 }, { at: 1100, pos: 90 },
    ]);
    expect(Math.round(r.unitsPerS)).toBe(800);
    expect(r.atMs).toBe(1100);
  });

  it('ignores two actions at the same instant', () => {
    // Not an infinite speed -- not a speed at all.
    const r = peakSpeed([{ at: 0, pos: 0 }, { at: 0, pos: 100 }]);
    expect(r.unitsPerS).toBe(0);
  });

  it('has no answer for fewer than two actions', () => {
    expect(peakSpeed([])).toBeNull();
    expect(peakSpeed([{ at: 0, pos: 0 }])).toBeNull();
    expect(peakSpeed(null)).toBeNull();
  });
});
