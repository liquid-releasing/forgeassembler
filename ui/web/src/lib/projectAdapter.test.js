import { describe, it, expect } from 'vitest';
import {
  toForgeProject, fromForgeProject, fromDetected, fromForgeBundleSegment,
  msToTimecode, timecodeToMs, segmentHasChannel,
  channelGroup, projectChannelCoverage, channelGapsFor, NEUTRAL_KELVIN,
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


describe('channelGroup mirrors the backend buckets', () => {
  it('names the categorised channels', () => {
    expect(channelGroup('main')).toBe('main');
    expect(channelGroup('twist')).toBe('multi_axis');
    expect(channelGroup('alpha')).toBe('three_phase_estim');
    expect(channelGroup('beta-prostate')).toBe('prostate');
    expect(channelGroup('pulse_frequency')).toBe('pulse_frequency');
  });
  it('sends device and parameter tracks to "other" — they still forge', () => {
    for (const ch of ['handy', 'shaker', 'volume', 'frequency',
                      'pulse_rise_time', 'lovense', 'ossm', 'vacuglide']) {
      expect(channelGroup(ch)).toBe('other');
    }
  });
});

describe('projectChannelCoverage', () => {
  const project = (channelsA, channelsB, flags = {}) => ({
    channels: { main: true, multi_axis: true, estim_3p: true,
                prostate: true, pulse_freq: true, ...flags },
    sections: [{
      segments: [
        { id: 'a', kind: 'video', channels: channelsA },
        { id: 'b', kind: 'video', channels: channelsB },
        { id: 'card', kind: 'still', channels: [] },
      ],
    }],
  });

  it('counts every clip, ignoring stills', () => {
    const cov = projectChannelCoverage(project(['main'], ['main']));
    expect(cov.clips).toBe(2);
    const main = cov.groups.find(g => g.id === 'main').channels[0];
    expect(main).toMatchObject({ id: 'main', have: 2, eligible: 2, full: true });
  });

  it('reports a channel only one clip carries as a partial', () => {
    const cov = projectChannelCoverage(project(['main', 'twist'], ['main']));
    const axis = cov.groups.find(g => g.id === 'multi_axis');
    expect(axis.channels).toEqual([
      { id: 'twist', have: 1, eligible: 2, full: false },
    ]);
  });

  it('surfaces uncategorised device channels rather than dropping them', () => {
    const cov = projectChannelCoverage(
      project(['main', 'handy', 'shaker'], ['main', 'handy']));
    const other = cov.groups.find(g => g.id === 'other');
    expect(other.channels.map(c => c.id)).toEqual(['handy', 'shaker']);
    expect(other.included).toBe(true);   // "other" has no veto flag
    expect(cov.detected).toBe(3);        // main + handy + shaker
  });

  it('moves a vetoed group out of the detected count', () => {
    const cov = projectChannelCoverage(
      project(['main', 'alpha', 'beta'], ['main'], { estim_3p: false }));
    const estim = cov.groups.find(g => g.id === 'three_phase_estim');
    expect(estim.included).toBe(false);
    expect(cov.detected).toBe(1);
    expect(cov.vetoed).toBe(2);
  });

  it('lists no groups for a project with no clips', () => {
    expect(projectChannelCoverage({ sections: [] }))
      .toEqual({ groups: [], detected: 0, vetoed: 0, clips: 0 });
  });
});

describe('legacy channel flags are migrated on load', () => {
  // Everything-off-but-main was the OLD boot state, not a user choice —
  // no UI ever exposed these toggles. Read literally it forges one
  // funscript out of a 20-channel scene.
  const LEGACY = {
    version: '2.0', sections: [], output: { basename: 'x' },
    output_channels: {
      main: true, multi_axis: false, three_phase_estim: false,
      four_phase_estim: false, prostate: false, pulse_frequency: false,
    },
  };

  it('turns the legacy all-off shape back on', () => {
    const vm = fromForgeProject(LEGACY);
    expect(vm.channels).toMatchObject({
      main: true, multi_axis: true, estim_3p: true,
      estim_4p: true, prostate: true, pulse_freq: true,
    });
  });

  it('leaves a deliberate partial veto alone', () => {
    const vm = fromForgeProject({
      ...LEGACY,
      output_channels: { main: true, multi_axis: true, prostate: false },
    });
    expect(vm.channels.multi_axis).toBe(true);
    expect(vm.channels.prostate).toBe(false);
    expect(vm.channels.estim_3p).toBe(true);   // omitted == on
  });
});


describe('channelGapsFor', () => {
  const proj = {
    sections: [{
      segments: [
        { id: 'a', kind: 'video', channels: ['main', 'alpha', 'handy'] },
        { id: 'b', kind: 'video', channels: ['main', 'alpha'] },
        { id: 'card', kind: 'still', channels: [] },
      ],
    }],
  };

  it('names what a clip lacks that its neighbours have', () => {
    expect(channelGapsFor(proj.sections[0].segments[1], proj)).toEqual(['handy']);
  });

  it('is empty for the richest clip', () => {
    expect(channelGapsFor(proj.sections[0].segments[0], proj)).toEqual([]);
  });

  it('exempts stills in both directions', () => {
    // A title card is not "missing" anything...
    expect(channelGapsFor(proj.sections[0].segments[2], proj)).toEqual([]);
    // ...and its empty channel list never makes a neighbour look richer.
    const onlyStills = { sections: [{ segments: [
      { id: 'a', kind: 'video', channels: ['main'] },
      { id: 'card', kind: 'still', channels: [] },
    ] }] };
    expect(channelGapsFor(onlyStills.sections[0].segments[0], onlyStills)).toEqual([]);
  });

  it('survives a lone clip and a missing project', () => {
    const solo = { sections: [{ segments: [{ id: 'a', kind: 'video', channels: ['main'] }] }] };
    expect(channelGapsFor(solo.sections[0].segments[0], solo)).toEqual([]);
    expect(channelGapsFor(null, proj)).toEqual([]);
    expect(channelGapsFor({ id: 'x', kind: 'video', channels: [] }, null)).toEqual([]);
  });
});


describe('colour temperature is an offset in the view, Kelvin in the file', () => {
  // ffmpeg's colortemperature filter takes ABSOLUTE Kelvin and refuses
  // anything outside 1000..40000 — it doesn't clamp, it fails the whole
  // filter graph. Writing the UI's "+500 from neutral" straight into
  // color_temperature_k sent it 500 and killed the render.
  const seg = (json) => fromForgeProject({
    version: '2.0', output: { basename: 'x' },
    sections: [{ id: 's', leading_joiner: { id: 'j', joiner_type: 'none', params: {} },
                 segments: [{ id: 'a', video: 'C:/a.mp4', audio: { mode: 'keep' },
                              funscripts: { source: 'auto_detect' }, ...json }] }],
  }).sections[0].segments[0];

  it('reads absolute Kelvin as an offset from neutral', () => {
    expect(seg({ color_temperature_k: 5200 }).temp).toBe(5200 - NEUTRAL_KELVIN);
    expect(seg({}).temp).toBe(0);
  });

  it('writes the offset back as absolute Kelvin, inside ffmpeg range', () => {
    const out = toForgeProject({
      channels: {}, output: {},
      sections: [{ id: 's', joiner: { type: 'none' }, segments: [
        { id: 'a', file: 'C:/a.mp4', temp: 500, audio: 'keep' },
      ] }],
    });
    const k = out.sections[0].segments[0].color_temperature_k;
    expect(k).toBe(7000);
    expect(k).toBeGreaterThanOrEqual(1000);
    expect(k).toBeLessThanOrEqual(40000);
  });

  it('omits the field entirely at neutral, so no filter is applied', () => {
    const out = toForgeProject({
      channels: {}, output: {},
      sections: [{ id: 's', joiner: { type: 'none' }, segments: [
        { id: 'a', file: 'C:/a.mp4', temp: 0, audio: 'keep' },
      ] }],
    });
    expect(out.sections[0].segments[0].color_temperature_k).toBeUndefined();
  });
});


describe('schema fields with no UI survive a load/save', () => {
  // Output.bug / metadata / closing_joiner are real, implemented schema
  // fields that no control edits yet. They used to vanish: open a
  // CLI-made project in the GUI, save it, and the bug overlay was gone.
  const WITH_EXTRAS = {
    version: '2.0', sections: [],
    output_channels: { main: true },
    output: {
      folder: 'C:/out', basename: 'mix', resolution: '1080p', quality: 'high',
      frame_rate: '30', normalize_audio: true, produce_video: true,
      produce_funscripts: true, produce_audio_estim: true,
      bug: { file: 'C:/logo.png', corner: 'br', margin_px: 32, opacity: 0.8 },
      metadata: { title: 'Vol 3' },
      closing_joiner: { id: 'join-close', joiner_type: 'fade_to_black',
                        params: { duration_s: 2 } },
    },
  };

  it('round-trips them untouched', () => {
    const back = toForgeProject(fromForgeProject(WITH_EXTRAS));
    expect(back.output.bug).toEqual(WITH_EXTRAS.output.bug);
    expect(back.output.metadata).toEqual(WITH_EXTRAS.output.metadata);
    expect(back.output.closing_joiner).toEqual(WITH_EXTRAS.output.closing_joiner);
  });

  it('does not invent them for a project that has none', () => {
    const back = toForgeProject(fromForgeProject({
      version: '2.0', sections: [], output_channels: { main: true },
      output: { basename: 'mix' },
    }));
    expect('bug' in back.output).toBe(false);
    expect('metadata' in back.output).toBe(false);
    expect('closing_joiner' in back.output).toBe(false);
  });
});

