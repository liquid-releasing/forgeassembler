import { describe, expect, it } from 'vitest';

import {
  applyRemap,
  baseNameOf,
  commonRoot,
  describeMissing,
  mediaPathsOf,
  planRemap,
  remapPath,
} from './missingMedia';

const D = 'D:\\ai\\_forge ready\\_goonerguy.join\\New folder\\Session';

function seg(file, over = {}) {
  return { id: file, file, kind: 'video', title: baseNameOf(file), ...over };
}

describe('mediaPathsOf', () => {
  it('collects clips, branding, overlays and replacement audio', () => {
    const vm = {
      sections: [{
        segments: [seg(`${D}\\a.mp4`),
                   seg(`${D}\\b.mp4`, { audio: 'replace', audioFile: `${D}\\b.wav` })],
        overlaysList: [{ kind: 'image', file: 'D:\\brand\\logo.png' },
                       { kind: 'text', text: 'Thanks' }],
      }],
      output: {
        brandingIntro: { file: 'D:\\brand\\open.mp4' },
        brandingOutro: { file: 'D:\\brand\\close.mp4' },
        overlays: [{ kind: 'image', file: 'D:\\brand\\logo2.png' },
                   { kind: 'text', text: 'Credits' }],
      },
    };
    const paths = mediaPathsOf(vm).map((m) => m.path);

    expect(paths).toContain(`${D}\\a.mp4`);
    expect(paths).toContain(`${D}\\b.wav`);
    expect(paths).toContain('D:\\brand\\logo.png');
    expect(paths).toContain('D:\\brand\\open.mp4');
    expect(paths).toContain('D:\\brand\\close.mp4');
    expect(paths).toContain('D:\\brand\\logo2.png');
    // A text overlay has no file and must not be reported as a missing one:
    // seven files named above, two text overlays, seven paths.
    expect(paths).toHaveLength(7);
  });

  it('does not report a title card as a file', () => {
    // It is RENDERED, not read off disk. Reporting it missing would send
    // someone hunting for a file that was never supposed to exist.
    const vm = { sections: [{ segments: [{ id: 't', titleCard: true, file: '' }] }] };
    expect(mediaPathsOf(vm)).toEqual([]);
  });

  it('de-duplicates a file two clips share', () => {
    const vm = { sections: [{ segments: [seg(`${D}\\a.mp4`), seg(`${D}\\a.mp4`)] }] };
    expect(mediaPathsOf(vm)).toHaveLength(1);
  });

  it('de-duplicates across separator style and case, as Windows does', () => {
    const vm = {
      sections: [{ segments: [seg('D:\\clips\\a.mp4'), seg('d:/CLIPS/A.mp4')] }],
    };
    expect(mediaPathsOf(vm)).toHaveLength(1);
  });

  it('labels branding by which end it is', () => {
    const vm = { sections: [], output: { brandingOutro: { file: 'D:\\b\\c.mp4' } } };
    expect(mediaPathsOf(vm)[0]).toMatchObject({
      role: 'branding', label: 'closing branding',
    });
  });
});

describe('commonRoot', () => {
  it('finds the folder a set of clips shares', () => {
    expect(commonRoot([`${D}\\a.mp4`, `${D}\\b.mp4`, `${D}\\c.mp4`]))
      .toBe('D:/ai/_forge ready/_goonerguy.join/New folder/Session');
  });

  it('stops at the shallowest shared folder', () => {
    expect(commonRoot(['D:\\a\\b\\one.mp4', 'D:\\a\\c\\two.mp4'])).toBe('D:/a');
  });

  it('comes back as a drive root when only the drive is shared', () => {
    // This is the signal that a whole drive moved, not a folder.
    expect(commonRoot(['D:\\a\\one.mp4', 'D:\\b\\two.mp4'])).toBe('D:/');
  });

  it('is empty across two drives', () => {
    expect(commonRoot(['D:\\a\\one.mp4', 'E:\\a\\two.mp4'])).toBe('');
  });

  it('ignores case and separator when comparing', () => {
    expect(commonRoot(['D:\\Clips\\a.mp4', 'd:/clips/b.mp4'])).toBe('D:/Clips');
  });

  it('handles one path and none', () => {
    expect(commonRoot([`${D}\\a.mp4`]))
      .toBe('D:/ai/_forge ready/_goonerguy.join/New folder/Session');
    expect(commonRoot([])).toBe('');
  });
});

describe('describeMissing', () => {
  it('says nothing when nothing is missing', () => {
    // A bar that is always there stops being read.
    expect(describeMissing([], 40)).toBeNull();
  });

  it('names the DRIVE when every file is gone from one', () => {
    const missing = [{ path: 'D:\\a\\one.mp4' }, { path: 'D:\\b\\two.mp4' }];
    const d = describeMissing(missing, 2);
    expect(d.kind).toBe('drive');
    expect(d.detail).toContain('D:/');
    expect(d.detail).toMatch(/different letter/);
  });

  it('is a folder problem when only some are missing', () => {
    const missing = [{ path: 'D:\\a\\one.mp4' }, { path: 'D:\\a\\two.mp4' }];
    const d = describeMissing(missing, 10);
    expect(d.kind).toBe('folder');
    expect(d.detail).toContain('D:/a');
  });

  it('does not claim a drive moved when files merely share one', () => {
    // All missing, shared root is a real folder -- that folder moved, and
    // saying "check your drive letter" would send someone the wrong way.
    const missing = [{ path: 'D:\\a\\one.mp4' }, { path: 'D:\\a\\two.mp4' }];
    expect(describeMissing(missing, 2).kind).toBe('folder');
  });

  it('says so when they did not move together', () => {
    const missing = [{ path: 'D:\\a\\one.mp4' }, { path: 'E:\\b\\two.mp4' }];
    expect(describeMissing(missing, 5).kind).toBe('scattered');
  });

  it('counts one file in the singular', () => {
    const d = describeMissing([{ path: 'D:\\a\\one.mp4' }], 5);
    expect(d.title).toBe('1 file is missing.');
  });
});

describe('remapPath', () => {
  it('swaps one root for another', () => {
    expect(remapPath('D:\\a\\b\\c.mp4', 'D:\\a', 'E:\\archive\\a'))
      .toBe('E:\\archive\\a\\b\\c.mp4');
  });

  it('handles the drive-letter case, which is the whole point', () => {
    expect(remapPath('D:\\ai\\clips\\c.mp4', 'D:/', 'E:'))
      .toBe('E:\\ai\\clips\\c.mp4');
  });

  it('removes a folder level, which is what actually happened', () => {
    // `…\_goonerguy.join\New folder\Session\` became `…\_goonerguy.join\Session\`
    expect(remapPath(`${D}\\part2.mp4`, D,
                     'D:\\ai\\_forge ready\\_goonerguy.join\\Session'))
      .toBe('D:\\ai\\_forge ready\\_goonerguy.join\\Session\\part2.mp4');
  });

  it('matches the root case-insensitively and either way round', () => {
    expect(remapPath('d:/a/b/c.mp4', 'D:\\A', 'E:\\x')).toBe('E:\\x\\b\\c.mp4');
  });

  it('keeps the new root separator style rather than mixing them', () => {
    expect(remapPath('D:/a/b/c.mp4', 'D:/a', '/mnt/media'))
      .toBe('/mnt/media/b/c.mp4');
  });

  it('returns null for a path that is not under the old root', () => {
    // So a caller can tell "rewritten" from "left alone" without string
    // comparisons of its own.
    expect(remapPath('E:\\other\\c.mp4', 'D:\\a', 'E:\\x')).toBeNull();
  });

  it('does not treat a sibling folder as a match', () => {
    // `D:\archive2` must not match the root `D:\archive`.
    expect(remapPath('D:\\archive2\\c.mp4', 'D:\\archive', 'E:\\x')).toBeNull();
  });

  it('returns null rather than guessing on missing arguments', () => {
    expect(remapPath('', 'D:\\a', 'E:\\x')).toBeNull();
    expect(remapPath('D:\\a\\c.mp4', '', 'E:\\x')).toBeNull();
    expect(remapPath('D:\\a\\c.mp4', 'D:\\a', '')).toBeNull();
  });
});
