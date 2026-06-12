import { describe, it, expect } from 'vitest';
import {
  toForgeProject, fromForgeProject, fromDetected,
  msToTimecode, timecodeToMs,
} from './projectAdapter.js';

// A representative .forgeproject.json (the contract). real → view → real must
// preserve every field the schema defines.
const REAL = {
  version: '2.0',
  sections: [
    {
      id: 'sec-1',
      name: 'Opening',
      leading_joiner: { id: 'j-sec-1', joiner_type: 'none', params: {} },
      overlays: [],
      segments: [
        {
          id: 's1',
          video: 'C:/clips/steel.mp4',
          audio: { mode: 'keep' },
          overlays: [],
          funscripts_source: 'auto_detect',
          bookmark: 'Steel pour',
          color_temperature_k: 5200,
          trim_start: '00:00:01.500',
          trim_end: '00:00:06.250',
        },
      ],
    },
    {
      id: 'sec-2',
      name: 'Build',
      leading_joiner: {
        id: 'j-sec-2', joiner_type: 'fade_to_black',
        params: { duration_s: 2.5, fade_s: 1.0, color: '#000000' },
      },
      overlays: [],
      segments: [
        {
          id: 's2',
          video: 'C:/clips/title.png',
          audio: { mode: 'silence' },
          overlays: [],
          funscripts_source: 'auto_detect',
          still_duration_s: 5,
          bookmark: 'Title',
        },
      ],
    },
  ],
  output_channels: {
    main: true, multi_axis: false, three_phase_estim: true,
    four_phase_estim: false, prostate: true, pulse_frequency: false,
  },
  output: {
    folder: 'C:/out', basename: 'combined', resolution: '1440p',
    quality: 'high', frame_rate: '30', normalize_audio: true,
    produce_video: true, produce_funscripts: true, produce_audio_estim: false,
  },
  audio_beds: [],
};

describe('timecode helpers', () => {
  it('round-trips ms ↔ HH:MM:SS.mmm', () => {
    for (const ms of [0, 1500, 6250, 3661001, 59999]) {
      expect(timecodeToMs(msToTimecode(ms))).toBe(ms);
    }
  });
  it('formats with zero-padding', () => {
    expect(msToTimecode(6250)).toBe('00:00:06.250');
    expect(msToTimecode(3661001)).toBe('01:01:01.001');
  });
});

describe('real → view → real is lossless', () => {
  const back = toForgeProject(fromForgeProject(REAL));

  it('preserves output block', () => {
    expect(back.output).toEqual(REAL.output);
  });
  it('preserves output_channels', () => {
    expect(back.output_channels).toEqual(REAL.output_channels);
  });
  it('preserves sections, joiners, and segment fields', () => {
    expect(back.sections).toEqual(REAL.sections);
  });
  it('preserves version + audio_beds', () => {
    expect(back.version).toBe('2.0');
    expect(back.audio_beds).toEqual([]);
  });
});

describe('view → real basics', () => {
  it('maps name → basename and channel ids', () => {
    const vm = {
      name: 'myproj',
      output: { resolution: '4k', normalizeAudio: false, video: true, funscripts: false },
      channels: { main: true, estim_3p: true, audio_estim: false },
      sections: [],
      audioBeds: [],
    };
    const real = toForgeProject(vm);
    expect(real.output.basename).toBe('myproj');
    expect(real.output.resolution).toBe('4k');
    expect(real.output.normalize_audio).toBe(false);
    expect(real.output.produce_funscripts).toBe(false);
    expect(real.output.produce_audio_estim).toBe(false);
    expect(real.output_channels.main).toBe(true);
    expect(real.output_channels.three_phase_estim).toBe(true);
    expect(real.output_channels.multi_axis).toBe(false);
  });
});

describe('fromDetected', () => {
  it('maps a detect payload to view segments', () => {
    const payload = {
      clips: [
        {
          video: 'C:/clips/0.mp4', stem: '0',
          funscripts: { main: 'C:/clips/0.funscript', pitch: 'C:/clips/0.pitch.funscript' },
          audio_estim: { 'stereostim.wav': 'C:/clips/0.stereostim.wav' },
          channel_groups: { main: ['main'], multi_axis: ['pitch'] },
        },
        { video: 'C:/clips/card.png', stem: 'card', funscripts: {}, audio_estim: {} },
      ],
    };
    const segs = fromDetected(payload);
    expect(segs).toHaveLength(2);
    expect(segs[0].file).toBe('C:/clips/0.mp4');
    expect(segs[0].kind).toBe('video');
    expect(segs[0].channels).toEqual(['main', 'pitch']);
    expect(segs[0].audioEstim).toEqual(['stereostim.wav']);
    expect(segs[1].kind).toBe('still');
  });
});
