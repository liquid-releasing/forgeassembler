// Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

// Where a newly created segment lands in the project.
//
// Three ways to ask for a position, in precedence order:
//   1. anchored to a clip  — before / after it, or at the end of its section
//   2. aimed at a section  — top of that section
//   3. neither             — top of the whole sequence
//
// The default is the TOP, not the end. Title cards are the main thing
// created this way and a title card is a lead-in: dropping it after the
// last clip puts it where nobody asked for it.

/**
 * @param {object} project  view-model project ({ sections: [{ id, segments }] })
 * @param {object} seg      the segment to insert
 * @param {object} [ctx]    { anchorClipId, forSectionId }
 * @param {string} [insertionPoint] "before"|"after"|"end" when anchored;
 *                                  "start"|"end" when not
 * @returns {object} a new project — the input is never mutated
 */
export function insertSegment(project, seg, ctx = {}, insertionPoint = null) {
  const sections = project?.sections || [];
  if (!sections.length) return project;

  // 1. Anchored to a clip: position relative to it, inside its own section.
  if (ctx?.anchorClipId) {
    const ip = insertionPoint || 'after';
    return {
      ...project,
      sections: sections.map((s) => {
        const idx = s.segments.findIndex((c) => c.id === ctx.anchorClipId);
        if (idx === -1) return s;
        if (ip === 'end') return { ...s, segments: [...s.segments, seg] };
        const next = [...s.segments];
        next.splice(ip === 'before' ? idx : idx + 1, 0, seg);
        return { ...s, segments: next };
      }),
    };
  }

  // 2/3. A named section, or the sequence as a whole.
  const ip = insertionPoint || 'start';
  const targetId = ctx?.forSectionId
    || (ip === 'end' ? sections[sections.length - 1].id : sections[0].id);
  return {
    ...project,
    sections: sections.map((s) => (s.id !== targetId ? s : {
      ...s,
      segments: ip === 'end' ? [...s.segments, seg] : [seg, ...s.segments],
    })),
  };
}
