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

// Which video encoder this machine will use, and roughly how fast.
// Resolves to { encoder, hardware, label, rate_1080p, resolution_cost }.
// Cached for the session — probing spawns ffmpeg.
export function videoEncoder() {
  return dedupedCall('video_encoder', () =>
    call('video_encoder', {}, () => Promise.resolve(null)));
}

// List the `.forge` scenes in a folder. Resolves to
// { folder, bundles: [{path, stem}] } — shallow, so a folder of 50 scenes
// answers instantly; the caller imports them one at a time.
export function detectForgeFolder(path) {
  return dedupedCall(`detect_forge_folder::${path}`, () =>
    call('detect_forge_folder', { path }, () => Promise.resolve({ bundles: [] })));
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

// Where a generated thumbnail lives.
//
// Thumbnails are derived data, so they go in the OS cache directory
// rather than next to the user's media — a folder of scenes should not
// grow PNGs because you looked at it. The name is keyed on the source
// path and timestamp, so reopening a project reuses the frame instead
// of re-running ffmpeg, and two scenes cut from one source at different
// points still get their own.
//
// Returns null outside Tauri; the browser mock has no filesystem.
export async function thumbnailPathFor(video, atMs) {
  if (!isTauri()) return null;
  const { appCacheDir, join } = await import('@tauri-apps/api/path');
  // FNV-1a: short, stable across runs, and collision-resistant enough
  // for a cache whose worst failure is drawing the wrong 320px frame.
  let h = 0x811c9dc5;
  const key = String(video);
  for (let i = 0; i < key.length; i += 1) {
    h ^= key.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  const name = `${h.toString(16)}-${Math.round(atMs)}.png`;
  return join(await appCacheDir(), 'thumbs', name);
}

// The title layouts, themes and marks this build can render.
//
// Fetched rather than hardcoded for the reason `listJoiners` is: the
// ENGINE decides what it can draw, and a picker offering a layout the
// engine has never heard of is a bug waiting for a user to find it.
export function titleCatalog() {
  return dedupedCall('title_catalog', () =>
    call('title_catalog', {}, () => Promise.resolve(null)));
}

// Render one title card and return where it landed.
//
// `specJson` is the joiner's params as JSON — the same dict the project
// file holds and the forge reads, so the preview cannot interpret the
// settings differently from the render.
//
// The filename is a hash of the CONTENT, which does two jobs: the
// webview can never serve a stale card from its cache after an edit,
// and going back to a card you already looked at costs nothing.
//
// Returns null outside Tauri; the browser mock has no renderer.
export async function titleCardPreview(specJson, overFrame,
                                       width = 960, height = 540) {
  if (!isTauri()) return null;
  const { appCacheDir, join } = await import('@tauri-apps/api/path');
  const key = `${specJson}|${width}x${height}|${overFrame ? 'frame' : 'flat'}`;
  // FNV-1a, same as thumbnailPathFor.
  let h = 0x811c9dc5;
  for (let i = 0; i < key.length; i += 1) {
    h ^= key.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  const out = await join(await appCacheDir(), 'titlecards', `${h.toString(16)}.png`);
  const res = await dedupedCall(`title_preview::${h.toString(16)}`, () =>
    call('title_preview', { spec: specJson, out, width, height, overFrame },
         () => Promise.resolve(null)));
  return res ? { ...res, path: out } : null;
}

export function extractThumbnail(video, atMs, out) {
  return dedupedCall(`extract_thumbnail::${video}::${atMs}`, () =>
    call('extract_thumbnail', { video, atMs, out }, () => Promise.resolve(out)));
}

export function loadProject(path) {
  return dedupedCall(`load_project::${path}`, () =>
    call('load_project', { path }, () => Promise.resolve(null)));
}

// Summarise the combined funscript for the Build tab's live strip. Takes
// the project object, not a path, so the strip describes what is being
// edited right now rather than the last save. Resolves to
// { channel, duration_ms, action_count, avg_bpm, peak_speed, peak_velocity,
//   bins: [{speed, v, seg_id, section_id}] }.
export function previewProject(project, channel = 'main') {
  return call('preview_project', { project, channel }, () => Promise.resolve(null));
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
// `startDir` opens the dialog where you were last time. The Rust side
// ignores it when the path is no longer a directory -- a remembered
// folder can be on a drive that is not attached -- so callers may pass a
// stale one without checking.
export function pickFolder({ startDir = null } = {}) {
  return call('pick_folder', { startDir }, () => Promise.resolve(null));
}
export function pickFile({ title = null, filterName = null, extensions = null,
                            startDir = null } = {}) {
  return call('pick_file', { title, filterName, extensions, startDir },
              () => Promise.resolve(null));
}
export function pickSavePath(defaultName, { startDir = null } = {}) {
  return call('pick_save_path', { defaultName, startDir }, () => Promise.resolve(null));
}
export function revealPath(path) {
  return call('reveal_path', { path }, () => Promise.resolve());
}
export function openExternal(url) {
  return call('open_external', { url }, () => Promise.resolve());
}
