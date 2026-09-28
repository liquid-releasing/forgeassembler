import { describe, it, expect } from 'vitest';
import { tidyName, titleForClip, titleForFolder } from './titleDefaults.js';

describe('tidyName', () => {
  it('reads a slug as words', () => {
    expect(tidyName('its-just-ai-sex')).toBe('Its just ai sex');
    expect(tidyName('scene_two_final')).toBe('Scene two final');
  });

  it('drops decorative hyphen runs', () => {
    // A real name off the user's disk.
    expect(tidyName('-madmartigan----its-just-ai-sex'))
      .toBe('Madmartigan its just ai sex');
  });

  it('keeps a hyphen that joins two words', () => {
    // These are names, not decoration — `FOC-Stim` is what the device is
    // called, and a slug rule would rename it.
    expect(tidyName('FOC-Stim 4-phase')).toBe('FOC-Stim 4-phase');
  });

  it('leaves a name that was already written by a person', () => {
    // The whole point of the case rule: title-casing this would hand back
    // `It'S Just Ai Sex`.
    expect(tidyName("-Madmartigan- - It's Just AI Sex"))
      .toBe("Madmartigan It's Just AI Sex");
  });

  it('only capitalises when the name carried no case of its own', () => {
    expect(tidyName('eDging warmup')).toBe('eDging warmup');
    expect(tidyName('edging warmup')).toBe('Edging warmup');
  });

  it('survives nothing', () => {
    expect(tidyName('')).toBe('');
    expect(tidyName(null)).toBe('');
    expect(tidyName('---')).toBe('');
  });
});

describe('titleForClip', () => {
  it('prefers a bookmark, which is a name a person chose', () => {
    expect(titleForClip({ title: 'The Long Tease', file: 'C:/x/clip-01.mp4' }))
      .toBe('The Long Tease');
  });

  it('falls back to the file name without its extension', () => {
    expect(titleForClip({ file: "D:/rel/-madmartigan----its-just-ai-sex.mp4" }))
      .toBe('Madmartigan its just ai sex');
  });

  it('takes the basename off either separator', () => {
    expect(titleForClip({ file: 'D:\\rel\\deep\\slow-build.mp4' })).toBe('Slow build');
  });

  it('does not mistake a dotted stem for an extension it should keep', () => {
    expect(titleForClip({ file: '/x/best-of.v2.mp4' })).toBe('Best of.v2');
  });

  it('has nothing to say about nothing', () => {
    expect(titleForClip(null)).toBe('');
    expect(titleForClip({})).toBe('');
  });
});

describe('titleForFolder', () => {
  it('names the compilation after the folder it lives in', () => {
    expect(titleForFolder("D:\\__lqr_releases\\-Madmartigan- - It's Just AI Sex"))
      .toBe("Madmartigan It's Just AI Sex");
  });

  it('ignores a trailing separator', () => {
    expect(titleForFolder('D:/shows/late-night/')).toBe('Late night');
  });

  it('never strips an extension, because a folder has none', () => {
    expect(titleForFolder('D:/shows/My Show 2.0')).toBe('My Show 2.0');
  });
});
