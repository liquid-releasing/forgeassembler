// Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

import { describe, expect, it } from 'vitest';
import { parseProgressLine, stageProgress, makeStageTracker } from './forgeProgress';

describe('parseProgressLine', () => {
  it('reads duration and stage count off a meta line', () => {
    expect(parseProgressLine('meta: duration_ms=11000 stages=2'))
      .toEqual({ kind: 'meta', durationMs: 11000, stages: 2, weights: null });
  });

  it('tolerates a meta line carrying only one of the two fields', () => {
    expect(parseProgressLine('meta: duration_ms=500'))
      .toEqual({ kind: 'meta', durationMs: 500, stages: null, weights: null });
    expect(parseProgressLine('meta: stages=3'))
      .toEqual({ kind: 'meta', durationMs: null, stages: 3, weights: null });
  });

  it('strips the prefix off a stage line', () => {
    expect(parseProgressLine('progress: forging video at 1080p (GPU · NVIDIA NVENC)'))
      .toEqual({ kind: 'stage', text: 'forging video at 1080p (GPU · NVIDIA NVENC)' });
  });

  it('treats the terminator as its own kind, not a stage', () => {
    expect(parseProgressLine('progress: done')).toEqual({ kind: 'done' });
  });

  it('pulls encoded-so-far out of an ffmpeg status line', () => {
    const line = 'frame=  330 fps=278 q=25.0 Lsize=    5894KiB time=00:00:10.90 '
               + 'bitrate=4430.1kbits/s speed= 9.2x elapsed=0:00:01.18';
    expect(parseProgressLine(line)).toEqual({ kind: 'encoded', ms: 10900 });
  });

  it('handles hours — a feature-length compilation is the point', () => {
    expect(parseProgressLine('frame=1 time=01:23:45.50 bitrate=1'))
      .toEqual({ kind: 'encoded', ms: ((1 * 60 + 23) * 60 + 45) * 1000 + 500 });
  });

  it('accepts a status line with no fractional seconds', () => {
    expect(parseProgressLine('time=00:00:07')).toEqual({ kind: 'encoded', ms: 7000 });
  });

  it('ignores ffmpeg chatter that carries no timestamp', () => {
    expect(parseProgressLine('ffmpeg version 8.1-full_build-www.gyan.dev')).toBeNull();
    expect(parseProgressLine('  libavutil      60. 26.100 / 60. 26.100')).toBeNull();
  });

  it('does not mistake a bare "time=" inside another token for a status line', () => {
    expect(parseProgressLine('  atime=00:00:05.00 (not ffmpeg progress)')).toBeNull();
  });

  it('survives empty and nullish lines', () => {
    expect(parseProgressLine('')).toBeNull();
    expect(parseProgressLine(null)).toBeNull();
    expect(parseProgressLine(undefined)).toBeNull();
  });

  it('returns null for a malformed meta line rather than NaN', () => {
    expect(parseProgressLine('meta: something-else')).toBeNull();
  });

  it('reads the per-stage weights off the meta line', () => {
    const ev = parseProgressLine(
      'meta: duration_ms=3548178 stages=4 weights=0.8000,0.0200,0.1000,0.0800');
    expect(ev.kind).toBe('meta');
    expect(ev.durationMs).toBe(3548178);
    expect(ev.stages).toBe(4);
    expect(ev.weights).toEqual([0.8, 0.02, 0.1, 0.08]);
  });

  it('reports no weights when an older CLI omits them', () => {
    const ev = parseProgressLine('meta: duration_ms=1000 stages=2');
    expect(ev.weights).toBeNull();
  });
});

describe('stageProgress', () => {
  // The real shape: video, funscripts, e-stim audio, bundle.
  const W = [0.8, 0.02, 0.1, 0.08];

  it('gives the encode its real share of the bar', () => {
    // The bug this replaced: 88% through the video read as 22% overall,
    // because the video owned a flat quarter.
    expect(stageProgress({ stage: 1, stageCount: 4, weights: W, frac: 0.88 }))
      .toBeCloseTo(0.704, 3);
    expect(stageProgress({ stage: 1, stageCount: 4, weights: null, frac: 0.88 }))
      .toBeCloseTo(0.22, 3);
  });

  it('starts each stage where the previous ones ended', () => {
    expect(stageProgress({ stage: 2, stageCount: 4, weights: W, frac: 0 }))
      .toBeCloseTo(0.8, 6);
    expect(stageProgress({ stage: 3, stageCount: 4, weights: W, frac: 0 }))
      .toBeCloseTo(0.82, 6);
    expect(stageProgress({ stage: 4, stageCount: 4, weights: W, frac: 1 }))
      .toBeCloseTo(0.95, 6);   // capped
  });

  it('never claims completion — only the summary may', () => {
    expect(stageProgress({ stage: 4, stageCount: 4, weights: W, frac: 5 }))
      .toBeLessThan(1);
    expect(stageProgress({ stage: 99, stageCount: 4, weights: W, frac: 9 }))
      .toBeLessThanOrEqual(0.95);
  });

  it('falls back to equal slices without weights', () => {
    expect(stageProgress({ stage: 2, stageCount: 4, frac: 0.5 })).toBeCloseTo(0.375, 6);
  });

  it('clamps a nonsense fraction instead of walking backwards', () => {
    expect(stageProgress({ stage: 1, stageCount: 4, weights: W, frac: -3 })).toBe(0);
    expect(stageProgress({ stage: 0, stageCount: 0, frac: null })).toBe(0);
  });

  it('fills the whole bar when only one stage runs', () => {
    expect(stageProgress({ stage: 1, stageCount: 1, weights: [1], frac: 0.5 }))
      .toBeCloseTo(0.5, 6);
  });
});


describe('makeStageTracker', () => {
  const VIDEO = 'forging video at 4k (GPU)';
  const SCRIPTS = 'forging funscripts';
  const ESTIM = 'forging haptic-estim audio';

  it('advances once per distinct stage', () => {
    const t = makeStageTracker();
    expect(t.saw(VIDEO)).toBe(1);
    expect(t.saw(SCRIPTS)).toBe(2);
    expect(t.saw(ESTIM)).toBe(3);
  });

  it('IGNORES a stage it has already seen', () => {
    // The bug this exists for: every forge emits into one `fa:progress`
    // channel, and a double-click started two of them. The handler
    // counted stage lines, so two producers ran the counter to the end
    // of the list within a second and parked the bar near the top --
    // reported live as "a ribbon at like 90% in the first instant".
    const t = makeStageTracker();
    t.saw(VIDEO);
    t.saw(VIDEO);
    t.saw(VIDEO);
    expect(t.stage).toBe(1);
  });

  it('keeps two interleaved runs from running the bar to the end', () => {
    const t = makeStageTracker();
    // Forge A and forge B, a second apart, reporting the same stages.
    for (const line of [VIDEO, VIDEO, SCRIPTS, SCRIPTS]) t.saw(line);
    expect(t.stage).toBe(2);
    // With a 4-stage plan weighted 0.8 to the video, the bar is where
    // the second stage starts -- not five sixths of the way along.
    const at = stageProgress({
      stage: t.stage, stageCount: 4, weights: [0.8, 0.02, 0.1, 0.08], frac: 0,
    });
    expect(at).toBeCloseTo(0.8, 5);
  });

  it('survives a stage with no text', () => {
    const t = makeStageTracker();
    expect(t.saw(undefined)).toBe(1);
    expect(t.saw(null)).toBe(1);
  });
});
