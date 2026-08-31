// projectAdapter.js — the ONLY place the React view-model and the on-disk
// .forgeproject.json schema meet.
//
// The extracted UI holds a compact camelCase view-model (durMs, joiner:{type},
// audio:'keep', temp); the backend (forgeassembler_core/project.py) reads/writes
// snake_case dataclasses (leading_joiner, output_channels, color_temperature_k,
// trim_start "HH:MM:SS.mmm"). Rather than rewrite the JSX bindings, we translate
// at the load/save/forge boundary here.
//
// The .forgeproject.json is the contract, so the canonical guarantee is
// real → view → real losslessly for every field the schema defines. View-only
// affordances (section color, cached durMs of *video* segments, detected channel
// list) are not stored in the file and re-derive on load.

// view channel id ↔ OutputChannels field
const CHANNEL_MAP = {
  main: 'main',
  multi_axis: 'multi_axis',
  estim_3p: 'three_phase_estim',
  estim_4p: 'four_phase_estim',
  prostate: 'prostate',
  pulse_freq: 'pulse_frequency',
};
const CHANNEL_MAP_INV = Object.fromEntries(
  Object.entries(CHANNEL_MAP).map(([v, r]) => [r, v]));

/**
 * Does `seg` carry anything for the UI channel category `uiChannelId`?
 *
 * A segment's `channels` are RAW funscript channel names — pitch, alpha,
 * beta, handy — while the UI asks in categories: multi_axis, estim_3p. Only
 * `main` happens to spell the same both ways, which is why a naive
 * `channels.includes(id)` reported a 19-channel bundle as "2D main" and
 * nothing else. The backend already groups them; use its answer.
 */
export function segmentHasChannel(seg, uiChannelId) {
  if (!seg) return false;
  if (uiChannelId === 'audio_estim') {
    return !!((seg.audioEstim || []).length
      || Object.keys(seg.explicitAudioEstim || {}).length);
  }
  if ((seg.channels || []).includes(uiChannelId)) return true;
  const group = CHANNEL_MAP[uiChannelId];
  const groups = seg.channelGroups || {};
  return !!(group && Array.isArray(groups[group]) && groups[group].length);
}

const IMAGE_EXT = /\.(png|jpe?g|webp)$/i;

// ── time helpers: ms ↔ "HH:MM:SS.mmm" ─────────────────────────────────
export function msToTimecode(ms) {
  if (ms == null) return null;
  const total = Math.max(0, Math.round(ms));
  const h = Math.floor(total / 3600000);
  const m = Math.floor((total % 3600000) / 60000);
  const s = Math.floor((total % 60000) / 1000);
  const milli = total % 1000;
  const pad = (n, w = 2) => String(n).padStart(w, '0');
  return `${pad(h)}:${pad(m)}:${pad(s)}.${pad(milli, 3)}`;
}

export function timecodeToMs(tc) {
  if (!tc) return null;
  const m = /^(\d+):(\d{2}):(\d{2})(?:\.(\d{1,3}))?$/.exec(String(tc).trim());
  if (!m) return null;
  const [, h, mm, ss, frac = '0'] = m;
  return (((+h * 60) + +mm) * 60 + +ss) * 1000 + Number(frac.padEnd(3, '0'));
}

// ── segment ───────────────────────────────────────────────────────────
function segToReal(seg) {
  const isStill = seg.kind === 'still' || IMAGE_EXT.test(seg.file || '');
  // Funscripts ride NESTED under `funscripts: {source, files?, folder?}` to
  // match the backend schema (forgeassembler_core/project.py Segment). Explicit
  // segments (e.g. a `.forge` import) carry their channel→path map in `files`.
  const fsrc = seg.funscriptsSource || 'auto_detect';
  const funscripts = { source: fsrc };
  if (fsrc === 'explicit' && seg.explicitFunscripts && Object.keys(seg.explicitFunscripts).length) {
    funscripts.files = seg.explicitFunscripts;
  } else if (fsrc === 'auto_detect' && seg.funscriptsFolder) {
    funscripts.folder = seg.funscriptsFolder;
  }
  const out = {
    id: seg.id,
    video: seg.file,
    audio: {
      mode: seg.audio || 'keep',
      ...(seg.audioFile ? { file: seg.audioFile } : {}),
    },
    overlays: seg.overlaysList || [],
    funscripts,
  };
  if (seg.explicitAudioEstim && Object.keys(seg.explicitAudioEstim).length) {
    out.audio_estim = { files: seg.explicitAudioEstim };
  }
  if (isStill) out.still_duration_s = (seg.durMs ?? 5000) / 1000;
  if (seg.temp) out.color_temperature_k = seg.temp;
  if (seg.title) out.bookmark = seg.title;
  const ts = msToTimecode(seg.trimStartMs);
  const te = msToTimecode(seg.trimEndMs);
  if (ts && seg.trimStartMs) out.trim_start = ts;
  if (te && seg.trimEndMs != null) out.trim_end = te;
  return out;
}

function segFromReal(seg) {
  const isStill = seg.still_duration_s != null || IMAGE_EXT.test(seg.video || '');
  const fs = seg.funscripts || {};
  const explicit = fs.files || {};
  const v = {
    id: seg.id,
    file: seg.video,
    title: seg.bookmark || prettyStem(seg.video),
    kind: isStill ? 'still' : 'video',
    durMs: isStill ? Math.round((seg.still_duration_s ?? 5) * 1000) : 0,
    // Explicit (e.g. `.forge` import) segments know their channels up front;
    // auto-detect segments discover them later, so start empty.
    channels: Object.keys(explicit),
    overlays: (seg.overlays || []).length,
    overlaysList: seg.overlays || [],
    audio: seg.audio?.mode || 'keep',
    temp: seg.color_temperature_k || 0,
    funscriptsSource: fs.source || 'auto_detect',
    explicitFunscripts: explicit,
    // Haptic audio the bundle brought with it, channel key -> path. Kept on
    // the view model so the round-trip preserves it and the UI can tell a
    // clip that ships audio from one that doesn't.
    explicitAudioEstim: seg.audio_estim?.files || {},
  };
  if (fs.folder) v.funscriptsFolder = fs.folder;
  if (seg.audio?.file) v.audioFile = seg.audio.file;
  const ts = timecodeToMs(seg.trim_start);
  const te = timecodeToMs(seg.trim_end);
  if (ts != null) v.trimStartMs = ts;
  if (te != null) v.trimEndMs = te;
  return v;
}

function prettyStem(path) {
  if (!path) return 'clip';
  const base = String(path).replace(/\\/g, '/').split('/').pop();
  return base.replace(/\.[^.]+$/, '');
}

// ── section ─────────────────────────────────────────────────────────
function sectionToReal(sec) {
  const { type = 'none', ...params } = sec.joiner || {};
  return {
    id: sec.id,
    leading_joiner: { id: `j-${sec.id}`, joiner_type: type, params },
    segments: (sec.segments || []).map(segToReal),
    overlays: sec.overlays || [],
    ...(sec.title ? { name: sec.title } : {}),
  };
}

function sectionFromReal(sec) {
  const lj = sec.leading_joiner || { joiner_type: 'none', params: {} };
  return {
    id: sec.id,
    title: sec.name || '',
    color: '#ff8c42',
    joiner: { type: lj.joiner_type || 'none', ...(lj.params || {}) },
    segments: (sec.segments || []).map(segFromReal),
    overlays: sec.overlays || [],
  };
}

// ── legacy v1.0 migration ────────────────────────────────────────────
// Old projects stored a flat `items: [Segment | Joiner]` list. The backend
// (forgeassembler_core/project.py::_migrate_items_to_sections) auto-migrates
// these to v2.0 Sections on load — but `load_project` reads the file raw, so
// we mirror that same rule here on read. Rules (kept 1:1 with Python):
//   • a non-"none" joiner starts a new section, leading with that joiner;
//   • a "none" joiner is an absorbed inter-clip cut;
//   • the first section defaults to a "none" leading joiner.
function migrateItemsToSections(items) {
  const sections = [];
  let curSegs = [];
  let curLeading = { joiner_type: 'none', params: {} };
  let n = 0;
  for (const it of items || []) {
    if (it && it.type === 'joiner') {
      if ((it.joiner_type || 'none') === 'none') continue; // absorbed cut
      if (curSegs.length || sections.length) {
        sections.push({ id: `sec-${n++}`, leading_joiner: curLeading, segments: curSegs });
      }
      curSegs = [];
      curLeading = { joiner_type: it.joiner_type, params: it.params || {} };
    } else if (it) {
      curSegs.push(it); // anything else is a segment
    }
  }
  if (curSegs.length || !sections.length) {
    sections.push({ id: `sec-${n++}`, leading_joiner: curLeading, segments: curSegs });
  }
  return sections;
}

// ── project ─────────────────────────────────────────────────────────
export function toForgeProject(vm, { folder = null } = {}) {
  const vch = vm.channels || {};
  const output_channels = {};
  for (const [vk, rk] of Object.entries(CHANNEL_MAP)) {
    output_channels[rk] = !!vch[vk];
  }
  return {
    version: '2.0',
    sections: (vm.sections || []).map(sectionToReal),
    output_channels,
    output: {
      folder: vm.output?.folder ?? folder,
      basename: vm.name || 'combined',
      resolution: vm.output?.resolution || '1080p',
      quality: vm.output?.quality || 'medium',
      frame_rate: vm.output?.frameRate || 'source',
      normalize_audio: vm.output?.normalizeAudio ?? true,
      produce_video: vm.output?.video ?? true,
      produce_funscripts: vm.output?.funscripts ?? true,
      produce_audio_estim: vch.audio_estim ?? true,
    },
    audio_beds: vm.audioBeds || [],
  };
}

export function fromForgeProject(json) {
  const oc = json.output_channels || {};
  const channels = {};
  for (const [rk, vk] of Object.entries(CHANNEL_MAP_INV)) {
    channels[vk] = !!oc[rk];
  }
  channels.audio_estim = json.output?.produce_audio_estim ?? true;
  return {
    name: json.output?.basename || 'combined',
    output: {
      folder: json.output?.folder ?? null,
      resolution: json.output?.resolution || '1080p',
      quality: json.output?.quality || 'medium',
      frameRate: json.output?.frame_rate || 'source',
      normalizeAudio: json.output?.normalize_audio ?? true,
      video: json.output?.produce_video ?? true,
      funscripts: json.output?.produce_funscripts ?? true,
    },
    channels,
    sections: (Array.isArray(json.sections)
      ? json.sections
      : migrateItemsToSections(json.items)).map(sectionFromReal),
    audioBeds: json.audio_beds || [],
  };
}

// ── forge bundle → view segment ─────────────────────────────────────
// `cli.py import-forge --format json` returns `segment` as a real Segment dict
// (funscripts.source = "explicit", funscripts.files = {channel: path}). It maps
// straight through segFromReal — the explicit channel map + video relink come
// across intact.
/**
 * A `.forge` import payload -> one view segment.
 *
 * `cli.py import-forge --format json` returns the Segment plus everything
 * else the bundle carries. The extras are what make a preview open fast:
 * `audio.json` (waveform peaks) and `beats.json` save re-deriving analysis
 * from the video, and `thumbnails/hero.png` is a real picture for the clip
 * row. Paths point into the bundle's extraction cache.
 *
 * @param {object} realSegment  payload.segment
 * @param {object} [payload]    the whole import payload, for the extras
 */
export function fromForgeBundleSegment(realSegment, payload = null) {
  if (!realSegment) return null;
  const v = segFromReal(realSegment);
  if (!payload) return v;
  const sidecars = payload.sidecars || {};
  const thumbnails = payload.thumbnails || {};
  if (thumbnails.hero) v.thumbPath = thumbnails.hero;
  if (Object.keys(thumbnails).length) v.thumbnails = thumbnails;
  if (Object.keys(sidecars).length) v.sidecars = sidecars;
  // The backend's grouping of the raw channel names, so the UI can ask by
  // category without re-deriving it.
  if (payload.channel_groups) v.channelGroups = payload.channel_groups;
  if (payload.duration_ms) v.durMs = payload.duration_ms;
  // A bundle with no analysis sidecars still previews — just slowly, by
  // decoding the video. Flagged so the UI can say so and point at a
  // re-export rather than leaving the user to wonder.
  v.bundleLean = !sidecars.audio;
  return v;
}

// ── detect → view segments ──────────────────────────────────────────
// Map a `cli.py detect --format json` payload into view-model segments the
// Build tab can drop into a section.
export function fromDetected(detectPayload) {
  const clips = detectPayload?.clips || [];
  return clips.map((clip, i) => {
    const isStill = IMAGE_EXT.test(clip.video || '');
    return {
      id: `seg-${clip.stem || i}-${i}`,
      file: clip.video,
      title: clip.stem || prettyStem(clip.video),
      kind: isStill ? 'still' : 'video',
      durMs: isStill ? 5000 : 0, // probed lazily after drop
      channels: Object.keys(clip.funscripts || {}),
      channelGroups: clip.channel_groups || {},
      audioEstim: Object.keys(clip.audio_estim || {}),
      overlays: 0,
      overlaysList: [],
      audio: 'keep',
      temp: 0,
    };
  });
}
