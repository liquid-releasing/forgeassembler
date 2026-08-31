// Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

// Adapt a `.forge` bundle's analysis sidecars to what forgemoment's
// MediaViewer expects.
//
// The two sides hold the same data in different casing. FunscriptForge
// writes these sidecars on disk in snake_case, and its Rust bridge hands
// them to the viewer through structs marked `#[serde(rename_all =
// "camelCase")]`. ForgeAssembler reads the same files straight out of the
// bundle, so it has to do that rename itself.
//
// Every function tolerates null: a lean bundle ships no sidecars at all, and
// the viewer treats a missing prop as "derive it or do without" rather than
// as an error.

/**
 * `audio.json` -> MediaViewer's `audioWaveform`.
 *
 * The viewer only draws a waveform when there are peaks, so an empty or
 * malformed sidecar has to come back as null rather than as an object with
 * an empty array — otherwise it renders an empty lane instead of hiding it.
 *
 * @returns {{hopMs: number, durationMs: number, peaks: number[],
 *            peakCount: number, fromSidecar: boolean}|null}
 */
export function toAudioWaveform(sidecar) {
  const peaks = sidecar?.peaks;
  if (!Array.isArray(peaks) || !peaks.length) return null;
  return {
    hopMs: sidecar.hop_ms ?? 10,
    durationMs: sidecar.duration_ms ?? 0,
    peaks,
    peakCount: sidecar.peak_count ?? peaks.length,
    fromSidecar: true,
  };
}

/**
 * `beats.json` -> MediaViewer's `beats`.
 *
 * @returns {{durationMs: number, bpm: number, beatsMs: number[],
 *            downbeatsMs: number[], fromSidecar: boolean}|null}
 */
export function toBeats(sidecar) {
  const beatsMs = sidecar?.beats_ms;
  if (!Array.isArray(beatsMs) || !beatsMs.length) return null;
  return {
    durationMs: sidecar.duration_ms ?? 0,
    bpm: sidecar.bpm ?? 0,
    beatsMs,
    downbeatsMs: Array.isArray(sidecar.downbeats_ms) ? sidecar.downbeats_ms : [],
    fromSidecar: true,
  };
}

/**
 * `chapters.json` -> the chapter list, for marking cut points against
 * structure the scene already knows about.
 *
 * FunscriptForge's schema has grown fields over time (stanzas, energy,
 * provenance); only what a viewer needs to place and label a chapter is
 * taken here, so a newer sidecar can't break the read.
 *
 * @returns {Array<{id: string, title: string, atMs: number, endMs: number,
 *                  color: string|null}>}
 */
export function toChapters(sidecar) {
  const chapters = sidecar?.chapters;
  if (!Array.isArray(chapters)) return [];
  return chapters.map((c, i) => ({
    id: c.id || `ch${i + 1}`,
    // An unnamed chapter is normal — detection names very few of them.
    title: (c.name || '').trim() || `Chapter ${i + 1}`,
    atMs: c.at_ms ?? 0,
    endMs: c.end_ms ?? 0,
    color: c.color || null,
  }));
}

/**
 * A funscript's actions, as MediaViewer's `funscript` prop wants them.
 * Bundle funscripts are ordinary `{actions: [{at, pos}]}` documents.
 */
export function toFunscript(doc) {
  const actions = doc?.actions;
  if (!Array.isArray(actions) || !actions.length) return null;
  return { actions };
}
