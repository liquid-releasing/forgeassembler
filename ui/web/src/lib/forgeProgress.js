// Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

// Classify one line of the forge progress stream.
//
// The CLI mixes three things into a single channel: `meta:` lines
// carrying data for the UI, `progress:` lines naming the stage in
// flight, and ffmpeg's own log. Only ffmpeg knows how far along a long
// encode is, and it says so in its status lines — which is where a real
// percentage comes from.

/**
 * @param {string} line one line from the `fa:progress` stream
 * @returns {{kind: 'meta', durationMs: number|null, stages: number|null,
 *            weights: number[]|null}
 *          |{kind: 'stage', text: string}
 *          |{kind: 'done'}
 *          |{kind: 'encoded', ms: number}
 *          |null} null when the line carries nothing the UI needs
 */
export function parseProgressLine(line) {
  const text = String(line || '');

  if (text.startsWith('meta:')) {
    const d = /duration_ms=(\d+)/.exec(text);
    const s = /stages=(\d+)/.exec(text);
    // Each stage's share of the bar, in stage order, summing to 1. Absent
    // from older CLIs, in which case the UI falls back to equal slices.
    const w = /weights=([\d.,]+)/.exec(text);
    if (!d && !s && !w) return null;
    const weights = w
      ? w[1].split(',').map(Number).filter(n => Number.isFinite(n) && n > 0)
      : null;
    return {
      kind: 'meta',
      durationMs: d ? Number(d[1]) : null,
      stages: s ? Number(s[1]) : null,
      weights: weights && weights.length ? weights : null,
    };
  }

  if (text.startsWith('progress:')) {
    const stage = text.replace(/^progress:\s*/, '');
    // "done" terminates the run; it isn't a stage, and counting it as
    // one stole a slice of the bar from the last real stage.
    return stage === 'done' ? { kind: 'done' } : { kind: 'stage', text: stage };
  }

  // ffmpeg status line — how much of the output exists so far:
  //   frame=  330 fps=278 q=25.0 Lsize=  5894KiB time=00:00:10.90 …
  const t = /\btime=(\d+):(\d{2}):(\d{2})(?:\.(\d+))?/.exec(text);
  if (t) {
    const ms = ((Number(t[1]) * 60 + Number(t[2])) * 60 + Number(t[3])) * 1000
             + (t[4] ? Math.round(Number(`0.${t[4]}`) * 1000) : 0);
    return { kind: 'encoded', ms };
  }

  return null;
}

/**
 * Which stage a run is in, from the stage lines it has seen.
 *
 * Keyed on the stage's TEXT rather than a counter, because the counter
 * could be driven by someone else's run: every forge emits into one
 * `fa:progress` channel, so two of them at once had the bar at the end
 * of the stage list within a second. Ticking on identity instead means a
 * duplicate stream re-reports a stage already seen and moves nothing.
 *
 * Monotonic on purpose — a bar that walks backwards reads as a fault.
 */
export function makeStageTracker() {
  const seen = new Set();
  return {
    /** @returns {number} the 1-based stage index after this line */
    saw(text) {
      seen.add(String(text || ''));
      return seen.size;
    },
    get stage() { return seen.size; },
  };
}

/**
 * Where the progress bar sits while stage `stage` (1-based) is `frac` of
 * the way through its own work.
 *
 * This lives here rather than inline in the forge handler for the same
 * reason lib/forgeGate.js does: nothing in this suite mounts a component,
 * so arithmetic written inside App.jsx cannot be tested — and this
 * arithmetic was wrong in a way that survived exactly because of that.
 *
 * `weights` is each stage's share of the bar, in stage order. Without it
 * every stage gets an equal slice, which is what the CLI's older `meta:`
 * line implies and what this did before: on a 4-stage run the video encode
 * owned a quarter of the bar while taking four fifths of the time, so a
 * nearly-finished 4K render reported "22%".
 *
 * Capped below 1 because only the final summary may claim completion; a
 * bar that reaches 100% while work continues is a lie the user acts on.
 */
export function stageProgress({ stage, stageCount, weights, frac, cap = 0.95 }) {
  const n = Math.max(1, stageCount || 1);
  const i = Math.max(0, (stage || 0) - 1);
  const shareOf = (k) => (weights && weights[k] > 0 ? weights[k] : 1 / n);
  let base = 0;
  for (let k = 0; k < i; k += 1) base += shareOf(k);
  const f = Math.min(1, Math.max(0, frac || 0));
  return Math.min(cap, base + shareOf(i) * f);
}
