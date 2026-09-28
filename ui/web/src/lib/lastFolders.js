// Where you were last time.
//
// Every picker opened wherever Windows last felt like, so adding the
// second folder of scenes meant navigating back across the drive, and
// saving the next output meant finding the output folder again. The app
// already knows both — it just threw them away.
//
// Kept beside `fa.recentProjects`, which is the same idea for files, and
// in localStorage for the same reason: it is a per-machine convenience,
// not project data. Nothing here may throw. localStorage is absent in
// the test runner, and in a private window the accessor itself can
// raise, so every path degrades to "no memory" rather than taking a
// file dialog down with it.

const KEY = 'fa.lastFolders';

/** Where a file lives. Returns null when there is no parent to take. */
export function parentFolder(path) {
  if (typeof path !== 'string' || !path) return null;
  // Windows and POSIX separators both, because a project file can carry
  // either depending on where it was written.
  const trimmed = path.replace(/[\\/]+$/, '');
  const cut = Math.max(trimmed.lastIndexOf('\\'), trimmed.lastIndexOf('/'));
  if (cut <= 0) return null;
  const parent = trimmed.slice(0, cut);
  // "C:" alone is not a folder; "C:\" is.
  return /^[A-Za-z]:$/.test(parent) ? `${parent}\\` : parent;
}

/** The file's own name, off either separator. */
export function baseName(path) {
  if (typeof path !== 'string' || !path) return '';
  // `lastIndexOf` rather than a regex, for the reason `parentFolder` uses
  // it: a character class is one escaping slip away from matching only the
  // forward slash, and the App's save message shipped exactly that -- so
  // "Saved ..." printed the whole of a Windows path instead of the name.
  const trimmed = path.replace(/[\\/]+$/, '');
  const cut = Math.max(trimmed.lastIndexOf('\\'), trimmed.lastIndexOf('/'));
  return cut < 0 ? trimmed : trimmed.slice(cut + 1);
}

function readAll() {
  try {
    const raw = localStorage.getItem(KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

/**
 * The folder last used for `kind`, or null.
 * Kinds in use: 'scenes' (where .forge scenes are imported from),
 * 'output' (where forged results are written), 'project' (where
 * .forgeproject.json files live).
 */
export function lastFolder(kind) {
  const v = readAll()[kind];
  return typeof v === 'string' && v ? v : null;
}

/** Remember a FOLDER for `kind`. */
export function rememberFolder(kind, folder) {
  if (!kind || typeof folder !== 'string' || !folder) return;
  try {
    localStorage.setItem(KEY, JSON.stringify({ ...readAll(), [kind]: folder }));
  } catch {
    /* no memory this run; the dialog still opens */
  }
}

/** Remember the folder a FILE was picked from. */
export function rememberFileFolder(kind, filePath) {
  const folder = parentFolder(filePath);
  if (folder) rememberFolder(kind, folder);
}

/** Forget everything. Exposed for a future "reset" and for tests. */
export function forgetFolders() {
  try { localStorage.removeItem(KEY); } catch { /* nothing to forget */ }
}
