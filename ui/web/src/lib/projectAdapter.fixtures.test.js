// projectAdapter.fixtures.test.js — exercises the adapter against the REAL
// on-disk .forgeproject.json fixtures (v1.0 `items` and v2.0 `sections`),
// plus migration/edge cases that mirror
// forgeassembler_core/project.py::_migrate_items_to_sections.
import { describe, it, expect } from 'vitest';
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import {
  toForgeProject, fromForgeProject, fromDetected,
  msToTimecode, timecodeToMs,
} from './projectAdapter.js';

// Repo root is four levels up from ui/web/src/lib/.
const REPO = fileURLToPath(new URL('../../../../', import.meta.url));
const loadJson = (rel) => JSON.parse(readFileSync(REPO + rel, 'utf8'));

const FIXTURES = {
  lqrMarketing: 'test_media/lqr_marketing.forgeproject.json',   // v1.0 items
  victoriaoats: 'test_media/victoriaoats/victoriaoats.forgeproject.json', // v1.0 (may be absent)
  combined: 'output/combined.forgeproject.json',                // v2.0 sections
};

// ── well-formed view-model invariants ────────────────────────────────
function assertWellFormed(vm) {
  expect(Array.isArray(vm.sections)).toBe(true);
  expect(vm.sections.length).toBeGreaterThan(0);
  expect(typeof vm.channels).toBe('object');
  expect(vm.channels).not.toBeNull();
  for (const sec of vm.sections) {
    expect(sec.joiner).toBeTruthy();
    expect(typeof sec.joiner.type).toBe('string');
    expect(Array.isArray(sec.segments)).toBe(true);
    for (const seg of sec.segments) {
      expect(typeof seg.file).toBe('string');
      expect(seg.file.length).toBeGreaterThan(0);
      expect(['video', 'still']).toContain(seg.kind);
    }
  }
}

describe('real fixtures → fromForgeProject yields a well-formed view-model', () => {
  it('v1.0 lqr_marketing.forgeproject.json (items schema)', () => {
    const vm = fromForgeProject(loadJson(FIXTURES.lqrMarketing));
    assertWellFormed(vm);
  });

  it('v2.0 combined.forgeproject.json (sections schema)', () => {
    const vm = fromForgeProject(loadJson(FIXTURES.combined));
    assertWellFormed(vm);
  });

  // The task lists a victoriaoats fixture, but it is not present on disk in
  // this checkout. Guard so the suite stays green; assert if it ever lands.
  const voPath = REPO + FIXTURES.victoriaoats;
  (existsSync(voPath) ? it : it.skip)(
    'v1.0 victoriaoats.forgeproject.json (items schema)', () => {
      const vm = fromForgeProject(JSON.parse(readFileSync(voPath, 'utf8')));
      assertWellFormed(vm);
    });
});

describe('v2.0 combined fixture round-trips losslessly', () => {
  const json = loadJson(FIXTURES.combined);
  const back = toForgeProject(fromForgeProject(json));

  it('preserves output_channels (the schema fields)', () => {
    // adapter only knows the CHANNEL_MAP fields; audio_estim is carried in
    // output.produce_audio_estim, not output_channels, so compare the mapped set.
    const mapped = (oc) => ({
      main: !!oc.main, multi_axis: !!oc.multi_axis,
      three_phase_estim: !!oc.three_phase_estim,
      four_phase_estim: !!oc.four_phase_estim,
      prostate: !!oc.prostate, pulse_frequency: !!oc.pulse_frequency,
    });
    expect(mapped(back.output_channels)).toEqual(mapped(json.output_channels));
  });

  it('preserves the output block', () => {
    expect(back.output.folder).toBe(json.output.folder);
    expect(back.output.basename).toBe(json.output.basename);
    expect(back.output.resolution).toBe(json.output.resolution);
    expect(back.output.quality).toBe(json.output.quality);
    expect(back.output.frame_rate).toBe(json.output.frame_rate);
    expect(back.output.normalize_audio).toBe(json.output.normalize_audio);
    expect(back.output.produce_video).toBe(json.output.produce_video);
    expect(back.output.produce_funscripts).toBe(json.output.produce_funscripts);
  });

  it('uses the canonical output.produce_audio_estim; treats output_channels.audio_estim as vestigial', () => {
    // NOT a bug: per forgeassembler_core/project.py, OutputChannels.audio_estim
    // was a Phase-2 placeholder that "never got wired through" — it moved to
    // Output.produce_audio_estim in v0.0.4, and OutputChannels.to_dict() no
    // longer emits it. This combined.forgeproject.json fixture is STALE: it
    // still carries the dead output_channels.audio_estim:false and lacks
    // produce_audio_estim. The adapter correctly ignores the dead flag and
    // falls back to the backend default (true), and writes audio_estim to the
    // canonical output.produce_audio_estim — never back into output_channels.
    expect(json.output.produce_audio_estim).toBeUndefined();
    expect(json.output_channels.audio_estim).toBe(false); // vestigial, ignored on read
    const vm = fromForgeProject(json);
    expect(vm.channels.audio_estim).toBe(true);                 // canonical default
    expect(back.output.produce_audio_estim).toBe(true);         // written to the canonical field
    expect(back.output_channels.audio_estim).toBeUndefined();   // dead flag not re-emitted
  });

  it('preserves section count, ids, joiner types, and segment videos', () => {
    expect(back.sections).toHaveLength(json.sections.length);
    json.sections.forEach((s, i) => {
      expect(back.sections[i].id).toBe(s.id);
      expect(back.sections[i].leading_joiner.joiner_type)
        .toBe(s.leading_joiner.joiner_type);
      expect(back.sections[i].segments.map((g) => g.video))
        .toEqual(s.segments.map((g) => g.video));
    });
  });

  it('round-trips overlays present on the third section', () => {
    const withOverlays = json.sections.find((s) => (s.overlays || []).length);
    expect(withOverlays).toBeTruthy();
    const ri = json.sections.indexOf(withOverlays);
    expect(back.sections[ri].overlays).toEqual(withOverlays.overlays);
  });
});

describe('v1.0 lqr_marketing migration matches the Python rule', () => {
  const json = loadJson(FIXTURES.lqrMarketing);
  const vm = fromForgeProject(json);

  // items: [seg-steel, fade, seg-banner(still), fade, seg-mechanical, fade, seg-closing]
  // No "none" joiners here; every fade splits → 4 sections of 1 segment each.
  it('splits into 4 sections (one per fade-separated clip)', () => {
    expect(vm.sections).toHaveLength(4);
    expect(vm.sections.map((s) => s.segments.length)).toEqual([1, 1, 1, 1]);
  });

  it('first section has a default "none" leading joiner', () => {
    expect(vm.sections[0].joiner.type).toBe('none');
  });

  it('subsequent sections are led by the splitting fade joiner', () => {
    for (let i = 1; i < vm.sections.length; i++) {
      expect(vm.sections[i].joiner.type).toBe('fade_to_black');
    }
    // join-3 had duration_s 2.0 → leads the closing section.
    expect(vm.sections[3].joiner.duration_s).toBe(2.0);
  });

  it('classifies the .png banner as a still, .mp4 clips as video', () => {
    const kinds = vm.sections.flatMap((s) => s.segments.map((g) => g.kind));
    expect(kinds).toEqual(['video', 'still', 'video', 'video']);
  });

  it('carries segment overlays through unchanged', () => {
    // seg-steel-pour had one image overlay.
    expect(vm.sections[0].segments[0].overlaysList).toHaveLength(1);
    expect(vm.sections[0].segments[0].overlays).toBe(1);
  });

  it('carries replace-audio file on the mechanical clip', () => {
    const mech = vm.sections[2].segments[0];
    expect(mech.audio).toBe('replace');
    expect(mech.audioFile).toMatch(/funscriptmechanicalaudio\.mp3$/);
  });
});

describe('migration: a "none" joiner is absorbed (not a section split)', () => {
  // Synthetic v1.0 mirroring the existing unit test but verifying the absorb
  // path against real loadJson plumbing-free helpers.
  const V1 = {
    version: '1.0',
    output: { basename: 'mix' },
    output_channels: { main: true },
    items: [
      { id: 'a', type: 'segment', video: 'C:/a.mp4', audio: { mode: 'keep' } },
      { id: 'cut', type: 'joiner', joiner_type: 'none', params: {} },
      { id: 'b', type: 'segment', video: 'C:/b.mp4', audio: { mode: 'keep' } },
      { id: 'fade', type: 'joiner', joiner_type: 'crossfade', params: { duration_s: 1.5 } },
      { id: 'c', type: 'segment', video: 'C:/c.mp4', audio: { mode: 'keep' } },
    ],
  };
  const vm = fromForgeProject(V1);

  it('absorbs the "none" cut into section 0 (a + b together)', () => {
    expect(vm.sections).toHaveLength(2);
    expect(vm.sections[0].segments.map((s) => s.file)).toEqual(['C:/a.mp4', 'C:/b.mp4']);
    expect(vm.sections[1].segments.map((s) => s.file)).toEqual(['C:/c.mp4']);
  });
  it('the crossfade leads section 1', () => {
    expect(vm.sections[1].joiner.type).toBe('crossfade');
    expect(vm.sections[1].joiner.duration_s).toBe(1.5);
  });
});

describe('fromDetected edge cases', () => {
  it('handles an empty clips list', () => {
    expect(fromDetected({ clips: [] })).toEqual([]);
    expect(fromDetected({})).toEqual([]);
    expect(fromDetected(null)).toEqual([]);
  });

  it('classifies every image extension as a still', () => {
    const exts = ['png', 'jpg', 'jpeg', 'webp', 'PNG', 'JPG'];
    const payload = {
      clips: exts.map((e, i) => ({ video: `C:/img${i}.${e}`, stem: `img${i}` })),
    };
    const segs = fromDetected(payload);
    expect(segs.every((s) => s.kind === 'still')).toBe(true);
    expect(segs.every((s) => s.durMs === 5000)).toBe(true);
    expect(segs.every((s) => typeof s.id === 'string' && s.id.length)).toBe(true);
  });

  it('maps multi-axis + estim channel groups on a video clip', () => {
    const payload = {
      clips: [{
        video: 'C:/clips/scene.mp4', stem: 'scene',
        funscripts: {
          main: 'C:/clips/scene.funscript',
          pitch: 'C:/clips/scene.pitch.funscript',
          roll: 'C:/clips/scene.roll.funscript',
        },
        audio_estim: {
          'stereostim.wav': 'C:/clips/scene.stereostim.wav',
          'threephase.wav': 'C:/clips/scene.threephase.wav',
        },
        channel_groups: { main: ['main'], multi_axis: ['pitch', 'roll'], estim: ['stereostim'] },
      }],
    };
    const [seg] = fromDetected(payload);
    expect(seg.kind).toBe('video');
    expect(seg.durMs).toBe(0); // probed lazily after drop
    expect(seg.channels).toEqual(['main', 'pitch', 'roll']);
    expect(seg.audioEstim).toEqual(['stereostim.wav', 'threephase.wav']);
    expect(seg.channelGroups).toEqual({
      main: ['main'], multi_axis: ['pitch', 'roll'], estim: ['stereostim'],
    });
    expect(seg.id).toBe('seg-scene-0');
  });

  it('defaults channels/audioEstim to empty arrays when absent', () => {
    const [seg] = fromDetected({ clips: [{ video: 'C:/x.mp4', stem: 'x' }] });
    expect(seg.channels).toEqual([]);
    expect(seg.audioEstim).toEqual([]);
    expect(seg.channelGroups).toEqual({});
  });
});

describe('timecode helpers — extended ranges', () => {
  it('round-trips ms across hours, sub-second, and boundaries', () => {
    const cases = [0, 1, 999, 1000, 59999, 60000, 3599999, 3600000, 3661001, 36000000];
    for (const ms of cases) {
      expect(timecodeToMs(msToTimecode(ms))).toBe(ms);
    }
  });

  it('formats hours and milliseconds with padding', () => {
    expect(msToTimecode(36000000)).toBe('10:00:00.000');
    expect(msToTimecode(3661001)).toBe('01:01:01.001');
    expect(msToTimecode(7)).toBe('00:00:00.007');
  });

  it('null / empty handling', () => {
    expect(msToTimecode(null)).toBeNull();
    expect(msToTimecode(undefined)).toBeNull();
    expect(timecodeToMs(null)).toBeNull();
    expect(timecodeToMs('')).toBeNull();
    expect(timecodeToMs('garbage')).toBeNull();
  });

  it('rounds and clamps negatives to zero', () => {
    expect(msToTimecode(-500)).toBe('00:00:00.000');
    expect(msToTimecode(1500.6)).toBe('00:00:01.501');
  });

  it('parses single-digit hour and fractional shorthands', () => {
    expect(timecodeToMs('1:02:03.5')).toBe(((1 * 60 + 2) * 60 + 3) * 1000 + 500);
    expect(timecodeToMs('00:00:06.25')).toBe(6250);
  });
});
