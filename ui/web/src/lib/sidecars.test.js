// Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

import { describe, expect, it } from 'vitest';
import { toAudioWaveform, toBeats, toChapters, toFunscript } from './sidecars';

// Shapes taken from a real bundle — averagejay v1's audio.json / beats.json /
// chapters.json — trimmed to a couple of entries.
const AUDIO = {
  version: '1.0', hop_ms: 10, duration_ms: 387880,
  peaks: [0.0, 0.13, 0.42], peak_count: 3,
  generated_by: { tool: 'videoflow.audio_peaks', method: 'rms' },
};
const BEATS = {
  version: '1.0', duration_ms: 384824, bpm: 143.5546875,
  beats_ms: [70, 488, 882], downbeats_ms: [70, 1695],
  generated_by: { tool: 'videoflow.audio_beats' },
};
const CHAPTERS = {
  version: '3.0',
  chapters: [
    { id: 'ch1', name: '', at_ms: 0, end_ms: 120000, color: '#4a90d9', tone: 'dominant' },
    { id: 'ch2', name: 'The Reveal', at_ms: 120000, end_ms: 387008, color: '#d94a4a' },
  ],
};

describe('toAudioWaveform', () => {
  it('renames the sidecar into what MediaViewer reads', () => {
    expect(toAudioWaveform(AUDIO)).toEqual({
      hopMs: 10, durationMs: 387880, peaks: [0.0, 0.13, 0.42],
      peakCount: 3, fromSidecar: true,
    });
  });

  it('defaults hop to 10ms when the sidecar omits it', () => {
    expect(toAudioWaveform({ peaks: [0.5] }).hopMs).toBe(10);
  });

  it('returns null with no peaks, so the viewer hides the lane', () => {
    expect(toAudioWaveform(null)).toBeNull();
    expect(toAudioWaveform({})).toBeNull();
    expect(toAudioWaveform({ peaks: [] })).toBeNull();
  });
});

describe('toBeats', () => {
  it('renames beats and downbeats', () => {
    expect(toBeats(BEATS)).toEqual({
      durationMs: 384824, bpm: 143.5546875,
      beatsMs: [70, 488, 882], downbeatsMs: [70, 1695], fromSidecar: true,
    });
  });

  it('tolerates a sidecar with beats but no downbeats', () => {
    expect(toBeats({ beats_ms: [1, 2] }).downbeatsMs).toEqual([]);
  });

  it('returns null when there are no beats', () => {
    expect(toBeats(null)).toBeNull();
    expect(toBeats({ bpm: 120, beats_ms: [] })).toBeNull();
  });
});

describe('toChapters', () => {
  it('maps chapters and names the unnamed ones by position', () => {
    const out = toChapters(CHAPTERS);
    expect(out).toHaveLength(2);
    expect(out[0]).toEqual({
      id: 'ch1', title: 'Chapter 1', atMs: 0, endMs: 120000, color: '#4a90d9',
    });
    expect(out[1].title).toBe('The Reveal');
  });

  it('ignores fields the schema has grown, rather than breaking on them', () => {
    const out = toChapters({ chapters: [{ id: 'c', name: 'x', at_ms: 1, end_ms: 2, stanzas: [], energy: {} }] });
    expect(out[0]).toEqual({ id: 'c', title: 'x', atMs: 1, endMs: 2, color: null });
  });

  it('returns an empty list for a bundle with no chapters sidecar', () => {
    expect(toChapters(null)).toEqual([]);
    expect(toChapters({})).toEqual([]);
  });
});

describe('toFunscript', () => {
  it('passes actions through', () => {
    expect(toFunscript({ actions: [{ at: 0, pos: 50 }] })).toEqual({ actions: [{ at: 0, pos: 50 }] });
  });

  it('returns null for an empty or missing script', () => {
    expect(toFunscript(null)).toBeNull();
    expect(toFunscript({ actions: [] })).toBeNull();
  });
});
