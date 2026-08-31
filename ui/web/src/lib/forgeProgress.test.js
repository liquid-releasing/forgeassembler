// Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

import { describe, expect, it } from 'vitest';
import { parseProgressLine } from './forgeProgress';

describe('parseProgressLine', () => {
  it('reads duration and stage count off a meta line', () => {
    expect(parseProgressLine('meta: duration_ms=11000 stages=2'))
      .toEqual({ kind: 'meta', durationMs: 11000, stages: 2 });
  });

  it('tolerates a meta line carrying only one of the two fields', () => {
    expect(parseProgressLine('meta: duration_ms=500'))
      .toEqual({ kind: 'meta', durationMs: 500, stages: null });
    expect(parseProgressLine('meta: stages=3'))
      .toEqual({ kind: 'meta', durationMs: null, stages: 3 });
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
});
