// A project's BRANDING, saved on its own so it can be re-used.
//
// Branding is the one part of a compilation that is the same across every
// compilation you make: the title page, the bumper at each end, the logo and
// the credits over them. Rebuilding it by hand for each project is the kind
// of work that quietly drifts — one project's credits say `.com`, the next
// one's doesn't — and there was no way to carry it across at all.
//
// ── What a branding file holds ──
// Exactly the five `Output` fields that ARE the branding, in the ENGINE's
// shape rather than the app's:
//
//   opening_joiner   the compilation's own title page
//   closing_joiner   the closing transition (fade to black, …)
//   branding_intro   the `.forge` scene before the compilation
//   branding_outro   the `.forge` scene after it
//   overlays         every compilation-level logo/credit layer, anchors kept
//
// Engine shape on purpose: it is what the project file already carries, so
// `cli.py` could read one of these without a translation layer, and a person
// opening it in a text editor sees the same words the project uses.
//
// ── Why it goes through the project adapter ──
// `extractBranding` builds a throwaway project, converts it with the real
// `toForgeProject`, and lifts the five keys out; `applyBranding` does the
// reverse through `fromForgeProject`. That is deliberate. Writing a second
// serializer for these fields would be a copy of the hardest, most-corrected
// code in the app — joiner ids, title-card params, segment channel maps — and
// the copy would drift from the original on the first change to either.
//
// ── What it does NOT hold ──
// Resolution, frame rate, quality, folder, basename, channels or sections.
// Loading branding into a project must change the branding and nothing else;
// a preset that silently reset someone's output resolution would be a trap.

import { fromForgeProject, toForgeProject } from './projectAdapter';

// `.forgebranding`, one extension, for the reason `.forgeproject` is one:
// Windows reads only the LAST extension, so a `.branding.json` would be a
// plain JSON file to the shell and the Open dialog would list every sidecar
// in the folder beside the one file you wanted.
export const BRANDING_EXT = 'forgebranding';

export const BRANDING_FILTERS = [
  { name: 'ForgeAssembler branding', extensions: [BRANDING_EXT] },
];

// Bumped only when an OLD file would be read wrongly by new code. Readers
// accept anything they understand rather than demanding an exact match: a
// preset is the user's data, and refusing to load one over a version digit
// is worse than the risk it guards against.
export const BRANDING_VERSION = '1.0';

// The five fields, named once. Used by both directions and by the tests, so
// adding a sixth cannot be half-done.
export const BRANDING_KEYS = [
  'opening_joiner',
  'closing_joiner',
  'branding_intro',
  'branding_outro',
  'overlays',
];

const ILLEGAL = /[<>:"/\\|?*\u0000-\u001f]/g;

/** The filename a branding preset called `name` should be saved as. */
export function brandingFileName(name) {
  if (typeof name !== 'string') return `branding.${BRANDING_EXT}`;
  const base = name.replace(new RegExp(`\\.${BRANDING_EXT}$`, 'i'), '')
    .replace(ILLEGAL, '-').trim();
  return `${base || 'branding'}.${BRANDING_EXT}`;
}

/** Whether `vm` has any branding worth saving. */
export function hasBranding(vm) {
  const out = vm?.output || {};
  return Boolean(
    (out.openingJoiner && out.openingJoiner.kind && out.openingJoiner.kind !== 'none')
    || out.closingJoiner
    || out.brandingIntro
    || out.brandingOutro
    || (Array.isArray(out.overlays) && out.overlays.length > 0),
  );
}

/**
 * A branding document for `vm`, ready to write as JSON.
 *
 * `name` is a label for the preset, not a filename — it is what the Load
 * dialog shows, so "Liquid Releasing 2026" is a better answer than "lqr1".
 */
export function extractBranding(vm, { name = null } = {}) {
  // A project with no sections: `toForgeProject` only reads `output` and
  // `sections`, and an empty section list keeps it from walking clips that
  // have nothing to do with branding.
  const real = toForgeProject({ ...vm, sections: [] });
  const out = real.output || {};

  const doc = {
    kind: 'forgebranding',
    version: BRANDING_VERSION,
    name: name || vm?.name || 'branding',
    created: new Date().toISOString(),
  };
  // Present-only, matching the engine: `Output.to_dict` omits each of these
  // when it is unset, so a preset with no outro has no `branding_outro` key
  // rather than a null that a reader has to special-case.
  for (const key of BRANDING_KEYS) {
    if (out[key] !== undefined && out[key] !== null) {
      if (key === 'overlays' && !out.overlays.length) continue;
      doc[key] = out[key];
    }
  }
  return doc;
}

/** True when `doc` looks like something `applyBranding` can read. */
export function isBrandingDoc(doc) {
  if (!doc || typeof doc !== 'object') return false;
  if (doc.kind === 'forgebranding') return true;
  // Tolerate a hand-made file that just carries the fields. Refusing one
  // over a missing marker would be pedantry about the user's own data.
  return BRANDING_KEYS.some((k) => doc[k] !== undefined);
}

/**
 * `vm` with `doc`'s branding in place of its own.
 *
 * REPLACES rather than merges. Half-applied branding — the new intro with the
 * old credits still over it — is the shape of a mistake nobody would ask for,
 * and there is no way to tell from the file which half was meant.
 *
 * Returns the vm unchanged when `doc` is not branding.
 */
export function applyBranding(vm, doc) {
  if (!isBrandingDoc(doc)) return vm;

  const output = {};
  for (const key of BRANDING_KEYS) {
    output[key] = doc[key] ?? (key === 'overlays' ? [] : null);
  }
  // Back through the real adapter, so a title card's params, a joiner's id
  // and a segment's channels are read exactly as the project loader reads
  // them -- see the note at the top of this file.
  const branding = fromForgeProject({ version: '2.0', sections: [], output }).output;

  return {
    ...vm,
    output: {
      ...vm.output,
      openingJoiner: branding.openingJoiner,
      brandingIntro: branding.brandingIntro,
      brandingOutro: branding.brandingOutro,
      overlays: branding.overlays,
      // `closingJoiner` is carried opaquely by the adapter and only present
      // when set, so it has to be added and removed explicitly -- spreading
      // `vm.output` above would otherwise keep the old one forever.
      ...(doc.closing_joiner
        ? { closingJoiner: doc.closing_joiner }
        : { closingJoiner: undefined }),
    },
  };
}

/** A one-line summary of what a branding doc contains, for the UI. */
export function describeBranding(doc) {
  if (!isBrandingDoc(doc)) return 'Not a branding file.';
  const parts = [];
  if (doc.opening_joiner) parts.push('title page');
  if (doc.branding_intro) parts.push('intro scene');
  if (doc.branding_outro) parts.push('outro scene');
  const n = Array.isArray(doc.overlays) ? doc.overlays.length : 0;
  if (n) parts.push(`${n} overlay${n === 1 ? '' : 's'}`);
  if (doc.closing_joiner) parts.push('closing transition');
  return parts.length ? parts.join(' · ') : 'Nothing in it.';
}
