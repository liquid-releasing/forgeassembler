// forge.js — the single JS↔backend bridge for ForgeAssembler.
//
// Cloned from FunscriptForge's api/forge.js. Three runtimes:
//   • Tauri  → invoke() the Rust commands in src-tauri/src/commands.rs
//   • HTTP   → POST to VITE_API_BASE_URL/<command> (future web deploy)
//   • mock   → in-browser fallback so `npm run dev` works without Tauri
//
// All IPC dedup lives HERE (dedupedCall), never at call sites — a reload wipes
// the in-memory map, so consumers must not cache their own promises.

export function isTauri() {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
}

const HTTP_BASE = import.meta.env?.VITE_API_BASE_URL || null;

async function call(command, args, mockFn) {
  if (isTauri()) {
    const { invoke } = await import('@tauri-apps/api/core');
    return invoke(command, args);
  }
  if (HTTP_BASE) {
    const res = await fetch(`${HTTP_BASE}/${command}`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(args ?? {}),
    });
    return res.json();
  }
  if (mockFn) return mockFn();
  throw new Error(`forge.${command}: no backend available (not Tauri, no VITE_API_BASE_URL, no mock)`);
}

const _inflight = new Map();
function dedupedCall(key, runFn) {
  const existing = _inflight.get(key);
  if (existing) return existing;
  const p = (async () => runFn())().finally(() => _inflight.delete(key));
  _inflight.set(key, p);
  return p;
}

// ── Read/scan commands ────────────────────────────────────────────────
export function listJoiners() {
  return dedupedCall('list_joiners', () =>
    call('list_joiners', {}, () => Promise.resolve({ joiners: [] })));
}

export function detectFolder(path) {
  return dedupedCall(`detect_folder::${path}`, () =>
    call('detect_folder', { path }, () => Promise.resolve({ clips: [] })));
}

export function validateProject(path) {
  return dedupedCall(`validate_project::${path}`, () =>
    call('validate_project', { path }, () =>
      Promise.resolve({ ok: true, errors: [], warnings: [] })));
}

export function probeDuration(path) {
  return dedupedCall(`probe_duration::${path}`, () =>
    call('probe_duration', { path }, () => Promise.resolve(0)));
}

export function extractThumbnail(video, atMs, out) {
  return dedupedCall(`extract_thumbnail::${video}::${atMs}`, () =>
    call('extract_thumbnail', { video, atMs, out }, () => Promise.resolve(out)));
}

export function loadProject(path) {
  return dedupedCall(`load_project::${path}`, () =>
    call('load_project', { path }, () => Promise.resolve(null)));
}

// Read one analysis sidecar a `.forge` bundle carried (peaks / beats /
// chapters / phrases / characters), from its extraction cache. Resolves to
// null when the bundle didn't ship that one — a lean bundle has none, and
// the preview still works, just slower.
export function readSidecar(path) {
  if (!path) return Promise.resolve(null);
  return dedupedCall(`read_sidecar::${path}`, () =>
    call('read_sidecar', { path }, () => Promise.resolve(null)));
}

// Import a FunscriptForge `.forge` bundle as one Segment. Returns
// { stem, channels, channel_groups, duration_ms, media_resolved, video,
//   needs_video, segment }. `segment` is a real Segment dict when a video is
// resolvable (bundled media or `video` passed); otherwise null + needs_video.
export function importForgeBundle(bundle, { video = null } = {}) {
  return call('import_forge_bundle', { bundle, video },
    () => Promise.resolve({ stem: null, channels: [], needs_video: true, segment: null }));
}

// ── Write/mutate commands ─────────────────────────────────────────────
export function saveProject(path, project) {
  return call('save_project', { path, project }, () => Promise.resolve());
}

// Forge streams `fa:progress` events; subscribe with onForgeProgress() before
// calling. Resolves with the CLI's JSON summary string when the run completes.
export function forgeProject(projectPath, { output = null, basename = null } = {}) {
  return call('forge_project', { projectPath, output, basename },
    () => Promise.resolve('{"video":null,"funscripts":[],"audio_estim":[]}'));
}

export async function onForgeProgress(handler) {
  if (!isTauri()) return () => {};
  const { listen } = await import('@tauri-apps/api/event');
  return listen('fa:progress', (e) => handler(e.payload));
}

// ── Native dialogs + shell ────────────────────────────────────────────
export function pickFolder() {
  return call('pick_folder', {}, () => Promise.resolve(null));
}
export function pickFile({ title = null, filterName = null, extensions = null } = {}) {
  return call('pick_file', { title, filterName, extensions }, () => Promise.resolve(null));
}
export function pickSavePath(defaultName) {
  return call('pick_save_path', { defaultName }, () => Promise.resolve(null));
}
export function revealPath(path) {
  return call('reveal_path', { path }, () => Promise.resolve());
}
export function openExternal(url) {
  return call('open_external', { url }, () => Promise.resolve());
}
