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
 * @returns {{kind: 'meta', durationMs: number|null, stages: number|null}
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
    if (!d && !s) return null;
    return {
      kind: 'meta',
      durationMs: d ? Number(d[1]) : null,
      stages: s ? Number(s[1]) : null,
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
