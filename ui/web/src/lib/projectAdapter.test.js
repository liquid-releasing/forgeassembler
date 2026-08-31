import { describe, it, expect } from 'vitest';
import {
  toForgeProject, fromForgeProject, fromDetected, fromForgeBundleSegment,
  msToTimecode, timecodeToMs, segmentHasChannel,
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
          funscripts: { source: 'auto_detect' },
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
          funscripts: { source: 'auto_detect' },
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

describe('legacy v1.0 items → sections migration on load', () => {
  // Mirrors forgeassembler_core/project.py::_migrate_items_to_sections.
  const V1 = {
    version: '1.0',
    output: { folder: 'C:/out', basename: 'legacy', resolution: '1080p',
              normalize_audio: true, produce_video: true, produce_funscripts: false },
    output_channels: { main: true, multi_axis: false, three_phase_estim: false,
                       four_phase_estim: false, prostate: false, pulse_frequency: false },
    items: [
      { id: 'seg-a', type: 'segment', video: 'C:/a.mp4', audio: { mode: 'keep' } },
      { id: 'join-1', type: 'joiner', joiner_type: 'none', params: {} },        // absorbed cut
      { id: 'seg-b', type: 'segment', video: 'C:/b.png', still_duration_s: 5,
        audio: { mode: 'silence' } },
      { id: 'join-2', type: 'joiner', joiner_type: 'fade_to_black',
        params: { duration_s: 2.0, color: '#1a1a1a' } },
      { id: 'seg-c', type: 'segment', video: 'C:/c.mp4', audio: { mode: 'keep' } },
    ],
    audio_beds: [],
  };

  const vm = fromForgeProject(V1);

  it('splits on non-"none" joiners, absorbs "none" cuts', () => {
    // section 1 = a + b (none cut absorbed); section 2 led by fade = c
    expect(vm.sections).toHaveLength(2);
    expect(vm.sections[0].segments.map(s => s.file)).toEqual(['C:/a.mp4', 'C:/b.png']);
    expect(vm.sections[1].segments.map(s => s.file)).toEqual(['C:/c.mp4']);
  });
  it('first section defaults to a "none" leading joiner', () => {
    expect(vm.sections[0].joiner.type).toBe('none');
  });
  it('carries the splitting joiner as the new section leader', () => {
    expect(vm.sections[1].joiner.type).toBe('fade_to_black');
    expect(vm.sections[1].joiner.duration_s).toBe(2.0);
  });
  it('preserves segment kind (still vs video)', () => {
    expect(vm.sections[0].segments[1].kind).toBe('still');
    expect(vm.sections[1].segments[0].kind).toBe('video');
  });
});

describe('explicit funscripts (.forge import) round-trip nested', () => {
  // A real Segment dict as `cli.py import-forge` emits it.
  const realSeg = {
    id: 'seg-forge-1', type: 'segment', video: 'C:/clips/scene.mp4',
    audio: { mode: 'keep' }, overlays: [], bookmark: 'VictoriaOaks',
    funscripts: {
      source: 'explicit',
      files: {
        main: '/cache/motion.funscript',
        alpha: '/cache/stations/estim3p/scene.alpha.funscript',
        surge: '/cache/stations/tcode/scene.surge.funscript',
      },
    },
  };

  it('fromForgeBundleSegment surfaces the channel map + relinked video', () => {
    const v = fromForgeBundleSegment(realSeg);
    expect(v.file).toBe('C:/clips/scene.mp4');
    expect(v.title).toBe('VictoriaOaks');
    expect(v.funscriptsSource).toBe('explicit');
    expect(v.explicitFunscripts.alpha).toMatch(/scene\.alpha\.funscript$/);
    expect(v.channels.sort()).toEqual(['alpha', 'main', 'surge']);
  });

  it('returns null for a missing segment', () => {
    expect(fromForgeBundleSegment(null)).toBeNull();
  });

  it('view → real preserves nested funscripts.files (no silent drop)', () => {
    const vm = {
      name: 'p', output: {}, channels: { main: true },
      sections: [{ id: 's', title: '', joiner: { type: 'none' },
        segments: [fromForgeBundleSegment(realSeg)] }],
      audioBeds: [],
    };
    const real = toForgeProject(vm);
    const back = real.sections[0].segments[0];
    expect(back.funscripts.source).toBe('explicit');
    expect(back.funscripts.files).toEqual(realSeg.funscripts.files);
  });

  it('auto_detect segments stay nested with just a source', () => {
    const v = fromForgeBundleSegment({
      id: 'x', video: 'C:/a.mp4', funscripts: { source: 'auto_detect' },
    });
    const real = toForgeProject({
      sections: [{ id: 's', joiner: { type: 'none' }, segments: [v] }],
      channels: {}, output: {}, audioBeds: [],
    });
    expect(real.sections[0].segments[0].funscripts).toEqual({ source: 'auto_detect' });
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

// ── .forge bundle extras ─────────────────────────────────────────────
// A bundle carries far more than funscripts: its own stim audio, analysis
// sidecars that let a preview open without re-deriving anything, and a hero
// still. All of it used to be extracted and then dropped.
describe('fromForgeBundleSegment', () => {
  const segment = {
    id: 'seg-1',
    video: 'E:/clips/scene.mp4',
    bookmark: 'Scene',
    funscripts: { source: 'explicit', files: { main: '/cache/motion.funscript' } },
    audio_estim: { files: { 'mp3': '/cache/audio/stim.mp3' } },
  };
  const payload = {
    stem: 'Scene',
    duration_ms: 387099,
    sidecars: { audio: '/cache/audio.json', beats: '/cache/beats.json' },
    thumbnails: { hero: '/cache/thumbnails/hero.png', funscript: '/cache/thumbnails/funscript.png' },
  };

  it('keeps working when only the segment is passed', () => {
    const v = fromForgeBundleSegment(segment);
    expect(v.channels).toEqual(['main']);
    expect(v.thumbPath).toBeUndefined();
  });

  it('carries the hero still, the sidecars and the duration', () => {
    const v = fromForgeBundleSegment(segment, payload);
    expect(v.thumbPath).toBe('/cache/thumbnails/hero.png');
    expect(v.sidecars.audio).toBe('/cache/audio.json');
    expect(v.durMs).toBe(387099);
  });

  it('carries the bundle audio onto the view model', () => {
    expect(fromForgeBundleSegment(segment, payload).explicitAudioEstim)
      .toEqual({ 'mp3': '/cache/audio/stim.mp3' });
  });

  it('flags a bundle with no analysis sidecars as lean', () => {
    expect(fromForgeBundleSegment(segment, payload).bundleLean).toBe(false);
    expect(fromForgeBundleSegment(segment, { ...payload, sidecars: {} }).bundleLean).toBe(true);
  });

  it('round-trips the bundle audio back to the on-disk shape', () => {
    const v = fromForgeBundleSegment(segment, payload);
    const real = toForgeProject({
      name: 'p', output: {}, channels: {}, audioBeds: [],
      sections: [{ id: 's', joiner: { type: 'none' }, segments: [v] }],
    });
    expect(real.sections[0].segments[0].audio_estim)
      .toEqual({ files: { 'mp3': '/cache/audio/stim.mp3' } });
  });

  it('omits audio_estim entirely for a clip that has none', () => {
    const plain = fromForgeBundleSegment({ ...segment, audio_estim: undefined });
    const real = toForgeProject({
      name: 'p', output: {}, channels: {}, audioBeds: [],
      sections: [{ id: 's', joiner: { type: 'none' }, segments: [plain] }],
    });
    expect(real.sections[0].segments[0]).not.toHaveProperty('audio_estim');
  });
});

// ── channel categories ───────────────────────────────────────────────
// A segment's `channels` are raw funscript names; the UI asks in
// categories. Only "main" spells the same both ways, which is why a
// 19-channel bundle used to report as "2D main" and nothing else.
describe('segmentHasChannel', () => {
  const bundleSeg = {
    channels: ['main', 'pitch', 'roll', 'twist', 'alpha', 'beta', 'handy'],
    channelGroups: {
      main: ['main'],
      multi_axis: ['pitch', 'roll', 'twist'],
      three_phase_estim: ['alpha', 'beta'],
      other: ['handy'],
    },
    explicitAudioEstim: { 'mp3': '/cache/stim.mp3' },
  };

  it('matches a category via the backend grouping, not the raw name', () => {
    expect(segmentHasChannel(bundleSeg, 'multi_axis')).toBe(true);
    expect(segmentHasChannel(bundleSeg, 'estim_3p')).toBe(true);
  });

  it('still matches main, which spells the same either way', () => {
    expect(segmentHasChannel(bundleSeg, 'main')).toBe(true);
  });

  it('reports a category the segment has nothing for', () => {
    expect(segmentHasChannel(bundleSeg, 'estim_4p')).toBe(false);
    expect(segmentHasChannel(bundleSeg, 'pulse_freq')).toBe(false);
  });

  it('treats audio as its own thing — it is not a funscript group', () => {
    expect(segmentHasChannel(bundleSeg, 'audio_estim')).toBe(true);
    expect(segmentHasChannel({ ...bundleSeg, explicitAudioEstim: {} }, 'audio_estim')).toBe(false);
    expect(segmentHasChannel({ audioEstim: ['stereostim.wav'] }, 'audio_estim')).toBe(true);
  });

  it('falls back to raw names for segments with no grouping', () => {
    expect(segmentHasChannel({ channels: ['main'] }, 'main')).toBe(true);
    expect(segmentHasChannel({ channels: ['main'] }, 'multi_axis')).toBe(false);
  });

  it('survives a null segment', () => {
    expect(segmentHasChannel(null, 'main')).toBe(false);
  });
});
