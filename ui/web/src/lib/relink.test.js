import { describe, expect, it } from 'vitest';

import { applyRemap, planRemap } from './missingMedia';

// Windows paths in a JS string need doubled backslashes, and getting that
// wrong produces literals that silently contain a newline (`E:\new` is
// `E:`+LF+`ew`). Built from segments so the intent is visible and a typo
// cannot hide inside a long quoted path.
const OLD = 'D:\\old';
const NEW = 'E:\\new';
const old = (name) => `${OLD}\\${name}`;
const fresh = (name) => `${NEW}\\${name}`;

function vm() {
  return {
    sections: [{
      segments: [
        { id: 'a', file: old('a.mp4'), trimStartMs: 1500, thumbPath: '/cache/a.png' },
        { id: 'b', file: 'd:/OLD/b.mp4', audio: 'replace', audioFile: old('b.wav') },
        { id: 't', titleCard: true, file: '' },
      ],
      overlaysList: [{ kind: 'image', file: old('logo.png') },
                     { kind: 'text', text: 'hi' }],
    }],
    output: {
      resolution: '4k',
      brandingIntro: { id: 'bi', file: old('open.mp4') },
      overlays: [{ kind: 'image', file: old('logo2.png') }],
    },
  };
}

function mapping() {
  return new Map([
    [old('a.mp4'), fresh('a.mp4')],
    ['d:/OLD/b.mp4', fresh('b.mp4')],
    [old('b.wav'), fresh('b.wav')],
    [old('logo.png'), fresh('logo.png')],
    [old('logo2.png'), fresh('logo2.png')],
    [old('open.mp4'), fresh('open.mp4')],
  ]);
}

describe('applyRemap', () => {
  it('rewrites every kind of path it knows about', () => {
    const next = applyRemap(vm(), mapping());
    const segs = next.sections[0].segments;

    expect(segs[0].file).toBe(fresh('a.mp4'));
    expect(segs[1].file).toBe(fresh('b.mp4'));
    expect(segs[1].audioFile).toBe(fresh('b.wav'));
    expect(next.sections[0].overlaysList[0].file).toBe(fresh('logo.png'));
    expect(next.output.brandingIntro.file).toBe(fresh('open.mp4'));
    expect(next.output.overlays[0].file).toBe(fresh('logo2.png'));
  });

  it('matches a key whatever its case or separator', () => {
    // The project and the disk disagree about both, and a relink that
    // skipped `d:/x` while fixing `D:\x` would be worse than doing nothing.
    expect(applyRemap(vm(), mapping()).sections[0].segments[1].file)
      .toBe(fresh('b.mp4'));
  });

  it('drops the cached thumbnail of a clip it moved', () => {
    // It was extracted from the OLD path and is keyed on it, so it would
    // keep showing the old frame — or nothing — forever.
    const seg = applyRemap(vm(), mapping()).sections[0].segments[0];
    expect(seg.thumbPath).toBeNull();
    expect(seg.thumb).toBeNull();
  });

  it('leaves trims, audio mode and output settings alone', () => {
    // Relinking says where a file went. It is not a re-import.
    const next = applyRemap(vm(), mapping());
    expect(next.sections[0].segments[0].trimStartMs).toBe(1500);
    expect(next.sections[0].segments[1].audio).toBe('replace');
    expect(next.output.resolution).toBe('4k');
  });

  it('does not touch a title card or a text overlay', () => {
    const next = applyRemap(vm(), mapping());
    expect(next.sections[0].segments[2]).toEqual(vm().sections[0].segments[2]);
    expect(next.sections[0].overlaysList[1]).toEqual({ kind: 'text', text: 'hi' });
  });

  it('returns the project untouched for an empty mapping', () => {
    const v = vm();
    expect(applyRemap(v, new Map())).toBe(v);
    expect(applyRemap(v, null)).toBe(v);
  });

  it('leaves a path the mapping does not mention', () => {
    const only = new Map([[old('a.mp4'), fresh('a.mp4')]]);
    const next = applyRemap(vm(), only);
    expect(next.sections[0].segments[0].file).toBe(fresh('a.mp4'));
    expect(next.output.brandingIntro.file).toBe(old('open.mp4'));
  });
});

describe('planRemap', () => {
  it('maps what is under the old root and reports what is not', () => {
    const missing = [{ path: old('a.mp4') }, { path: old('b.mp4') },
                     { path: 'F:\\elsewhere\\c.mp4' }];
    const { mapping: plan, unresolved } = planRemap(missing, OLD, NEW);

    expect(plan.size).toBe(2);
    expect(plan.get(old('a.mp4'))).toBe(fresh('a.mp4'));
    expect(unresolved).toHaveLength(1);
    expect(unresolved[0].path).toBe('F:\\elsewhere\\c.mp4');
  });

  it('produces CANDIDATES, not answers', () => {
    // The caller has to check they exist. A relink that "succeeded" onto
    // forty paths that are also not there is the worst possible answer.
    const { mapping: plan } = planRemap([{ path: old('a.mp4') }],
                                        OLD, 'E:\\nowhere');
    expect(plan.get(old('a.mp4'))).toBe('E:\\nowhere\\a.mp4');
  });

  it('handles the drive-letter case across the whole project', () => {
    const missing = [{ path: 'D:\\ai\\one.mp4' }, { path: 'D:\\brand\\logo.png' }];
    const { mapping: plan, unresolved } = planRemap(missing, 'D:\\', 'E:');

    expect(unresolved).toHaveLength(0);
    expect(plan.get('D:\\ai\\one.mp4')).toBe('E:\\ai\\one.mp4');
    expect(plan.get('D:\\brand\\logo.png')).toBe('E:\\brand\\logo.png');
  });
});
