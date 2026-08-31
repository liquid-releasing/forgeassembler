// Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

import { describe, expect, it } from 'vitest';
import { insertSegment } from './placement';

const CARD = { id: 'card', title: 'Title card' };

function proj() {
  return {
    name: 'p',
    sections: [
      { id: 's1', segments: [{ id: 'a' }, { id: 'b' }] },
      { id: 's2', segments: [{ id: 'c' }] },
    ],
  };
}

const ids = (p, sec) => p.sections.find((s) => s.id === sec).segments.map((s) => s.id);

describe('insertSegment', () => {
  it('puts an unanchored card at the very top of the sequence', () => {
    const out = insertSegment(proj(), CARD);
    expect(ids(out, 's1')).toEqual(['card', 'a', 'b']);
    expect(ids(out, 's2')).toEqual(['c']);
  });

  it('puts it at the top of a named section', () => {
    const out = insertSegment(proj(), CARD, { forSectionId: 's2' });
    expect(ids(out, 's1')).toEqual(['a', 'b']);
    expect(ids(out, 's2')).toEqual(['card', 'c']);
  });

  it('still supports the end of the sequence when asked', () => {
    const out = insertSegment(proj(), CARD, {}, 'end');
    expect(ids(out, 's1')).toEqual(['a', 'b']);
    expect(ids(out, 's2')).toEqual(['c', 'card']);
  });

  it('inserts before an anchor clip', () => {
    const out = insertSegment(proj(), CARD, { anchorClipId: 'b' }, 'before');
    expect(ids(out, 's1')).toEqual(['a', 'card', 'b']);
  });

  it('inserts after an anchor clip, which is the anchored default', () => {
    expect(ids(insertSegment(proj(), CARD, { anchorClipId: 'a' }, 'after'), 's1'))
      .toEqual(['a', 'card', 'b']);
    expect(ids(insertSegment(proj(), CARD, { anchorClipId: 'a' }), 's1'))
      .toEqual(['a', 'card', 'b']);
  });

  it('sends an anchored card to the end of the anchor’s own section', () => {
    const out = insertSegment(proj(), CARD, { anchorClipId: 'a' }, 'end');
    expect(ids(out, 's1')).toEqual(['a', 'b', 'card']);
    expect(ids(out, 's2')).toEqual(['c']);
  });

  it('an anchor takes precedence over a section', () => {
    const out = insertSegment(proj(), CARD, { anchorClipId: 'c', forSectionId: 's1' }, 'before');
    expect(ids(out, 's1')).toEqual(['a', 'b']);
    expect(ids(out, 's2')).toEqual(['card', 'c']);
  });

  it('leaves the input project untouched', () => {
    const before = proj();
    insertSegment(before, CARD);
    expect(ids(before, 's1')).toEqual(['a', 'b']);
  });

  it('returns the project unchanged when there are no sections', () => {
    const empty = { name: 'p', sections: [] };
    expect(insertSegment(empty, CARD)).toBe(empty);
  });

  it('drops a card into an empty section without complaint', () => {
    const p = { sections: [{ id: 's1', segments: [] }] };
    expect(ids(insertSegment(p, CARD), 's1')).toEqual(['card']);
  });
});
