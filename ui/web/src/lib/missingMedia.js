// Which files a project needs, and which of them are not there.
//
// A project stores ABSOLUTE paths. That is the right call for a tool whose
// clips come from four drives at once, but it means a project is only as
// portable as the paths in it — and two ordinary things break them:
//
//   one folder moved   a handful of clips go missing, sharing a deep root
//   the drive changed  EVERY path goes missing, sharing a root of `D:\`
//
// The second is the one to design for. The same external drive is `D:` on one
// machine and `E:` on another, so a project carried between them is entirely
// broken on arrival while being entirely correct below the drive letter.
// Telling someone "40 clips are missing" there is useless; telling them "40
// clips, all under D:\" names the actual problem in one line.
//
// So everything here works in terms of the COMMON ROOT of what is missing.
// That single idea covers both cases and is what a relink can act on.
//
// Pure — no Tauri, no IO. The caller does the existence check (one batched
// `paths_exist`) and hands the answers back in.

// Windows compares paths case-insensitively and accepts either separator, so
// every comparison here goes through this. The original spelling is what gets
// stored; this is only ever used to decide whether two paths match.
function norm(p) {
  return String(p || '').replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase();
}

function splitDirs(p) {
  const parts = String(p || '').replace(/\\/g, '/').split('/');
  parts.pop();               // drop the filename
  return parts;
}

/** The filename at the end of a path, whichever separator it uses. */
export function baseNameOf(p) {
  return String(p || '').replace(/\\/g, '/').split('/').pop() || '';
}

/**
 * Every filesystem path this project depends on, de-duplicated.
 *
 * Returns `[{ path, role, label }]`. `role` is what the file IS, which is
 * what lets the banner say "3 clips and a logo" rather than "4 files".
 *
 * Covers the branding bumpers deliberately: they are timeline segments like
 * any other, and a bumper whose video moved fails the forge just as hard as
 * a scene's would — the engine's own `validate` walks `timeline_segments`
 * for exactly this reason.
 */
export function mediaPathsOf(vm) {
  const out = [];
  const seen = new Set();
  const add = (path, role, label) => {
    if (!path || typeof path !== 'string') return;
    const key = norm(path);
    if (seen.has(key)) return;
    seen.add(key);
    out.push({ path, role, label });
  };

  for (const sec of vm?.sections || []) {
    for (const seg of sec.segments || []) {
      // A title card is rendered, not read off disk — it has no source file
      // and must never be reported as missing.
      if (seg.titleCard) continue;
      add(seg.file, 'clip', seg.title || baseNameOf(seg.file));
      if (seg.audio === 'replace' && seg.audioFile) {
        add(seg.audioFile, 'audio', baseNameOf(seg.audioFile));
      }
    }
    for (const ov of sec.overlaysList || []) {
      if (ov.kind !== 'text') add(ov.file, 'overlay', baseNameOf(ov.file));
    }
  }

  const output = vm?.output || {};
  for (const which of ['brandingIntro', 'brandingOutro']) {
    const seg = output[which];
    if (seg?.file) {
      add(seg.file, 'branding',
          which === 'brandingIntro' ? 'opening branding' : 'closing branding');
    }
  }
  for (const ov of output.overlays || []) {
    if (ov.kind !== 'text') add(ov.file, 'overlay', baseNameOf(ov.file));
  }
  return out;
}

/**
 * The deepest folder every one of `paths` sits under, or '' when they share
 * nothing — different drives, which is a project someone assembled across
 * two disks and is not one problem to solve but several.
 *
 * Returned in the ORIGINAL spelling of the first path, because it is shown to
 * a person and `d:/ai/_forge ready` is not what they called it.
 */
export function commonRoot(paths) {
  const list = (paths || []).filter(Boolean);
  if (!list.length) return '';

  const first = splitDirs(list[0]);
  let depth = first.length;
  for (const p of list.slice(1)) {
    const parts = splitDirs(p);
    let i = 0;
    while (i < depth && i < parts.length
           && norm(first[i]) === norm(parts[i])) i += 1;
    depth = i;
    if (depth === 0) break;
  }
  if (depth === 0) return '';
  // A lone drive root keeps its trailing separator: `D:` is not a folder,
  // and showing it that way reads as a typo rather than as a drive.
  const root = first.slice(0, depth).join('/');
  return depth === 1 && /^[a-z]:$/i.test(root) ? `${root}/` : root;
}

/**
 * What to tell the user, given the missing entries and how many were checked.
 *
 * `null` when nothing is missing — the caller shows no banner at all rather
 * than a cheerful one, because a bar that is always there stops being read.
 */
export function describeMissing(missing, checkedCount) {
  const n = (missing || []).length;
  if (!n) return null;

  const all = checkedCount > 0 && n === checkedCount;
  const root = commonRoot(missing.map((m) => m.path));
  const noun = n === 1 ? 'file' : 'files';

  // Every path gone AND they share a drive root: this is the drive-letter
  // case, and saying so is the difference between a five-second fix and an
  // afternoon of wondering what corrupted the project.
  if (all && /^[a-z]:\/?$/i.test(root)) {
    return {
      count: n,
      root,
      kind: 'drive',
      title: `All ${n} ${noun} this project uses are missing.`,
      detail: `Every one of them is on ${root} — if this project came from `
            + `another machine, that drive is probably mounted under a `
            + `different letter here.`,
    };
  }
  if (root) {
    return {
      count: n,
      root,
      kind: 'folder',
      title: `${n} ${noun} ${n === 1 ? 'is' : 'are'} missing.`,
      detail: `All of them were under ${root}.`,
    };
  }
  return {
    count: n,
    root: '',
    kind: 'scattered',
    title: `${n} ${noun} ${n === 1 ? 'is' : 'are'} missing.`,
    detail: 'They are in different places, so they did not move together.',
  };
}

/**
 * `path` with `oldRoot` swapped for `newRoot`.
 *
 * Returns null when `path` is not under `oldRoot`, so a caller can tell the
 * difference between "rewritten" and "left alone" without comparing strings
 * itself. Keeps the separator style of `newRoot`: mixing `/` into a Windows
 * path works, but it is the kind of thing that looks like damage when
 * someone opens the project in a text editor.
 */
export function remapPath(path, oldRoot, newRoot) {
  if (!path || !oldRoot || !newRoot) return null;
  const np = norm(path);
  const nr = norm(oldRoot);
  if (np !== nr && !np.startsWith(`${nr}/`)) return null;

  const rest = String(path).replace(/\\/g, '/').slice(String(oldRoot).length)
    .replace(/^[/\\]+/, '');
  // The new root's own style wins -- but a bare drive letter ("E:") has no
  // style at all, and defaulting that to '/' turns every remapped Windows
  // path into a mixed one. Fall back to how the ORIGINAL path was written.
  const sep = String(newRoot).includes('\\') ? '\\'
    : String(newRoot).includes('/') ? '/'
      : String(path).includes('\\') ? '\\' : '/';
  const base = String(newRoot).replace(/[/\\]+$/, '');
  return rest ? `${base}${sep}${rest.split('/').join(sep)}` : base;
}

/**
 * `vm` with every path in `mapping` replaced.
 *
 * `mapping` is keyed by the ORIGINAL path; lookup is case- and
 * separator-insensitive, because the project and the disk disagree about
 * both and a relink that silently skipped `d:/x` while fixing `D:\x` would
 * be worse than one that did nothing.
 *
 * Touches only the path fields. Trims, audio modes, overlays and channel
 * maps are untouched — relinking is telling the project where a file went,
 * not re-importing it.
 */
export function applyRemap(vm, mapping) {
  if (!mapping || !mapping.size) return vm;
  const byKey = new Map();
  for (const [from, to] of mapping) byKey.set(norm(from), to);
  const to = (p) => (p ? byKey.get(norm(p)) || p : p);

  const out = {
    ...vm,
    sections: (vm.sections || []).map((sec) => ({
      ...sec,
      segments: (sec.segments || []).map((seg) => (seg.titleCard ? seg : {
        ...seg,
        file: to(seg.file),
        ...(seg.audioFile ? { audioFile: to(seg.audioFile) } : {}),
        // The cached thumbnail was extracted from the OLD path and is keyed
        // on it. Dropping it is what makes the card refill from the file
        // that is actually there now.
        ...(to(seg.file) !== seg.file ? { thumb: null, thumbPath: null } : {}),
      })),
      overlaysList: (sec.overlaysList || []).map((ov) => (
        ov.kind === 'text' ? ov : { ...ov, file: to(ov.file) })),
    })),
  };

  const output = vm.output || {};
  out.output = {
    ...output,
    overlays: (output.overlays || []).map((ov) => (
      ov.kind === 'text' ? ov : { ...ov, file: to(ov.file) })),
  };
  for (const which of ['brandingIntro', 'brandingOutro']) {
    const seg = output[which];
    if (seg?.file) out.output[which] = { ...seg, file: to(seg.file) };
  }
  return out;
}

/**
 * The remap `newRoot` implies for `missing`, and what it cannot reach.
 *
 * Returns `{ mapping, unresolved }` — candidate paths only. The caller must
 * check the candidates exist before applying: a root the user picked by hand
 * can be the wrong folder, and a relink that "succeeded" onto forty paths
 * that are also not there is the worst possible answer.
 */
export function planRemap(missing, oldRoot, newRoot) {
  const mapping = new Map();
  const unresolved = [];
  for (const entry of missing || []) {
    const next = remapPath(entry.path, oldRoot, newRoot);
    if (next) mapping.set(entry.path, next);
    else unresolved.push(entry);
  }
  return { mapping, unresolved };
}
