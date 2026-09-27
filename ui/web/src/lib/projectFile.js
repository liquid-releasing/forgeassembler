// What a ForgeAssembler project is CALLED.
//
// One module, because the name turns up in four places that must agree:
// the save dialog's default, the open dialog's filter, the title bar,
// and the Export tab's list of what gets written. They had four separate
// string literals, and the day the extension changed is the day that
// stops being free.
//
// `.forgeproject`, not `.forgeproject.json`. Windows looks only at the
// LAST extension, so the old name was a plain `.json` file as far as the
// shell was concerned: it could not be associated with this app, and an
// Open dialog offering "JSON" listed every sidecar in the folder next to
// the one file you wanted. A project is still JSON inside — anyone who
// wants to hand-edit one can rename it — and everything here reads both
// names, so projects you already have open untouched.

export const PROJECT_EXT = 'forgeproject';
export const LEGACY_PROJECT_SUFFIX = '.forgeproject.json';

/**
 * Filters for the native open dialog.
 *
 * TWO filters rather than one combined list, because a combined list
 * would have to include `json` to catch the legacy name — Windows
 * matches on the last extension only — and that puts every sidecar back
 * in the picker. The dialog shows the first by default and lets you
 * switch to the second when you want an older project.
 */
export const PROJECT_FILTERS = [
  { name: 'ForgeAssembler project', extensions: [PROJECT_EXT] },
  { name: 'Project (older .forgeproject.json)', extensions: ['json'] },
];

// Characters Windows will not accept in a filename. Replaced rather than
// stripped so two different project names cannot collapse into one file.
const ILLEGAL = /[<>:"/\\|?*\u0000-\u001f]/g;

/** Take either project extension off a bare name. No path handling. */
function stripProjectExt(base) {
  const lower = base.toLowerCase();
  if (lower.endsWith(LEGACY_PROJECT_SUFFIX)) {
    return base.slice(0, -LEGACY_PROJECT_SUFFIX.length);
  }
  if (lower.endsWith(`.${PROJECT_EXT}`)) {
    return base.slice(0, -(PROJECT_EXT.length + 1));
  }
  return base;
}

/**
 * The filename a project called `name` should be saved as.
 *
 * This takes a NAME, not a path, and deliberately does not split on
 * separators the way `projectDisplayName` does: a project called
 * "a/b" must become "a-b", not "b". Silently shortening a name to its
 * last segment would let two different projects land on one file.
 */
export function projectFileName(name) {
  if (typeof name !== 'string') return `untitled.${PROJECT_EXT}`;
  const base = stripProjectExt(name).replace(ILLEGAL, '-').trim();
  return `${base || 'untitled'}.${PROJECT_EXT}`;
}

/** Whether `path` looks like a project file, under either name. */
export function isProjectPath(path) {
  if (typeof path !== 'string' || !path) return false;
  const lower = path.toLowerCase();
  return lower.endsWith(`.${PROJECT_EXT}`) || lower.endsWith(LEGACY_PROJECT_SUFFIX);
}

/**
 * A project's name, with any path and either extension taken off.
 *
 * Order matters: the legacy suffix has to be tested first, or
 * "vol_03.forgeproject.json" comes back as "vol_03.forgeproject".
 */
export function projectDisplayName(pathOrName) {
  if (typeof pathOrName !== 'string' || !pathOrName) return '';
  return stripProjectExt(pathOrName.split(/[\\/]/).pop() || '');
}
