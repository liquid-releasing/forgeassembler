import { describe, expect, it } from 'vitest';

import {
  BRANDING_EXT,
  BRANDING_KEYS,
  applyBranding,
  brandingFileName,
  describeBranding,
  extractBranding,
  hasBranding,
  isBrandingDoc,
} from './branding';

function overlay(over = {}) {
  return {
    id: 'ov-1', kind: 'text', file: '', start_s: 3, duration_s: 4,
    fade_in_s: 1, fade_out_s: 1, position: 'bc', opacity: 1,
    text: 'Thanks\n\nPMVHaven.com', text_color: '#ffffff',
    font_size: 48, font_family: 'arial', anchor: 'outro', ...over,
  };
}

// A view-model segment: `file`, not `video` -- that is the engine's spelling
// and `segToReal` reads `seg.file`.
function segment(over = {}) {
  return {
    id: 'seg-brand', file: 'D:/branding/lqr_open.mp4', kind: 'video',
    channels: [], overlays: 0, overlaysList: [], audio: 'keep', ...over,
  };
}

function branded(over = {}) {
  return {
    name: 'lqr1',
    output: {
      resolution: '4k', quality: 'high', frameRate: '30',
      folderLayout: 'grouped',
      openingJoiner: { kind: 'title_card', durationS: 4, params: { title: 'Volume 1' } },
      brandingIntro: segment(),
      brandingOutro: segment({ id: 'seg-brand-out' }),
      overlays: [overlay()],
      ...over,
    },
    sections: [{ id: 's1', title: 'One', segments: [], overlays: [] }],
  };
}

describe('extractBranding', () => {
  it('carries the five branding fields and nothing else', () => {
    const doc = extractBranding(branded());
    for (const key of BRANDING_KEYS) {
      if (key === 'closing_joiner') continue; // not set in this fixture
      expect(doc[key], key).toBeDefined();
    }
    // The settings that are NOT branding must not ride along: loading a
    // preset must never reset someone's resolution.
    for (const leaked of ['resolution', 'quality', 'frame_rate', 'folder',
                          'basename', 'folder_layout', 'produce_video']) {
      expect(doc[leaked], leaked).toBeUndefined();
    }
    expect(doc.sections).toBeUndefined();
  });

  it('omits what is not set rather than writing nulls', () => {
    const doc = extractBranding({ name: 'p', output: { overlays: [] }, sections: [] });
    for (const key of BRANDING_KEYS) expect(key in doc).toBe(false);
  });

  it('labels itself so a reader can tell what it is', () => {
    const doc = extractBranding(branded(), { name: 'Liquid Releasing 2026' });
    expect(doc.kind).toBe('forgebranding');
    expect(doc.name).toBe('Liquid Releasing 2026');
    expect(isBrandingDoc(doc)).toBe(true);
  });

  it('survives JSON, which is how it actually travels', () => {
    const doc = JSON.parse(JSON.stringify(extractBranding(branded())));
    expect(isBrandingDoc(doc)).toBe(true);
  });
});

describe('applyBranding', () => {
  it('puts the branding into a project that had none', () => {
    const doc = extractBranding(branded());
    const bare = { name: 'other', output: { resolution: '1080p' }, sections: [] };
    const next = applyBranding(bare, doc);

    expect(next.output.openingJoiner.kind).toBe('title_card');
    expect(next.output.brandingIntro).toBeTruthy();
    expect(next.output.brandingOutro).toBeTruthy();
    expect(next.output.overlays).toHaveLength(1);
  });

  it('leaves everything that is not branding alone', () => {
    const bare = {
      name: 'other',
      output: { resolution: '1080p', quality: 'low', folderLayout: 'grouped' },
      sections: [{ id: 'a', segments: [], overlays: [] }],
    };
    const next = applyBranding(bare, extractBranding(branded()));

    expect(next.name).toBe('other');
    expect(next.output.resolution).toBe('1080p');
    expect(next.output.quality).toBe('low');
    expect(next.output.folderLayout).toBe('grouped');
    expect(next.sections).toBe(bare.sections);
  });

  it('REPLACES the old branding instead of merging with it', () => {
    // Half-applied branding -- a new intro with the old credits still over
    // it -- is the shape of a mistake nobody would ask for.
    const old = branded({
      overlays: [overlay({ id: 'ov-old', text: 'OLD' }),
                 overlay({ id: 'ov-old-2', text: 'ALSO OLD' })],
    });
    const incoming = extractBranding(branded({
      overlays: [overlay({ id: 'ov-new', text: 'NEW' })],
    }));
    const next = applyBranding(old, incoming);

    expect(next.output.overlays).toHaveLength(1);
    expect(next.output.overlays[0].text).toBe('NEW');
  });

  it('clears branding the incoming file does not have', () => {
    const empty = extractBranding({ name: 'p', output: {}, sections: [] });
    const next = applyBranding(branded(), empty);

    expect(next.output.brandingIntro).toBeNull();
    expect(next.output.brandingOutro).toBeNull();
    expect(next.output.overlays).toEqual([]);
    expect(next.output.openingJoiner.kind).toBe('none');
  });

  it('keeps an overlay anchored to the outro anchored', () => {
    // The anchor is the whole reason credits can be placed at all -- the
    // absolute time is unknowable until forge time.
    const next = applyBranding({ name: 'p', output: {}, sections: [] },
                               extractBranding(branded()));
    expect(next.output.overlays[0].anchor).toBe('outro');
  });

  it('settles after one round trip and then stops changing', () => {
    // The FIRST pass normalises: a segment with no bookmark comes back with
    // one derived from its filename. That is the adapter doing its job, and
    // the engine reads a bookmark equal to the stem as derived rather than
    // chosen. What matters is that it converges -- saving the same branding
    // twice must give the same file, or every save looks like an edit.
    const first = applyBranding({ name: 'p', output: {}, sections: [] },
                                extractBranding(branded()));
    const once = extractBranding(first);
    const twice = extractBranding(applyBranding(
      { name: 'p', output: {}, sections: [] }, once));

    for (const key of BRANDING_KEYS) {
      expect(twice[key], key).toEqual(once[key]);
    }
  });

  it('leaves a bumper bookmark matching its filename, so the chapter stays "End"', () => {
    // A round trip fills `bookmark` in from the filename stem. The engine
    // treats a bookmark that merely repeats the stem as DERIVED, not chosen,
    // and names the closing chapter "End" -- so this must stay equal to the
    // stem rather than becoming something that looks deliberate.
    const next = applyBranding({ name: 'p', output: {}, sections: [] },
                               extractBranding(branded()));
    const doc = extractBranding(next);
    expect(doc.branding_outro.bookmark).toBe('lqr_open');
    expect(doc.branding_outro.video).toBe('D:/branding/lqr_open.mp4');
  });

  it('refuses a file that is not branding', () => {
    const vm = branded();
    expect(applyBranding(vm, { version: '2.0', sections: [], output: {} })).toBe(vm);
    expect(applyBranding(vm, null)).toBe(vm);
    expect(applyBranding(vm, 'nope')).toBe(vm);
  });

  it('accepts a hand-made file carrying only the fields', () => {
    const doc = { overlays: [overlay()] };
    expect(isBrandingDoc(doc)).toBe(true);
    expect(applyBranding({ name: 'p', output: {}, sections: [] }, doc)
      .output.overlays).toHaveLength(1);
  });
});

describe('hasBranding', () => {
  it('is false for an empty project', () => {
    expect(hasBranding({ output: {} })).toBe(false);
    expect(hasBranding({ output: { openingJoiner: { kind: 'none' } } })).toBe(false);
    expect(hasBranding({})).toBe(false);
  });

  it('is true for any one piece of it', () => {
    expect(hasBranding({ output: { overlays: [overlay()] } })).toBe(true);
    expect(hasBranding({ output: { brandingIntro: segment() } })).toBe(true);
    expect(hasBranding({ output: { openingJoiner: { kind: 'title_card' } } })).toBe(true);
  });
});

describe('brandingFileName', () => {
  it('uses one extension, so the shell can see it', () => {
    expect(brandingFileName('Liquid Releasing')).toBe(`Liquid Releasing.${BRANDING_EXT}`);
  });

  it('replaces illegal characters rather than dropping them', () => {
    // Dropping would let two different presets collapse onto one file.
    expect(brandingFileName('a/b')).toBe(`a-b.${BRANDING_EXT}`);
  });

  it('does not double the extension', () => {
    expect(brandingFileName(`lqr.${BRANDING_EXT}`)).toBe(`lqr.${BRANDING_EXT}`);
  });

  it('falls back on an empty or junk name', () => {
    expect(brandingFileName('')).toBe(`branding.${BRANDING_EXT}`);
    expect(brandingFileName(null)).toBe(`branding.${BRANDING_EXT}`);
  });
});

describe('describeBranding', () => {
  it('says what is in it', () => {
    const text = describeBranding(extractBranding(branded()));
    expect(text).toContain('title page');
    expect(text).toContain('intro scene');
    expect(text).toContain('outro scene');
    expect(text).toContain('1 overlay');
  });

  it('says so when there is nothing', () => {
    expect(describeBranding(extractBranding({ name: 'p', output: {}, sections: [] })))
      .toBe('Nothing in it.');
  });
});
