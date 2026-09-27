/* @esm-converted */
import React from 'react';
import { Button, Icon } from './primitives';
import { FA_DATA } from './data';
import { toMediaUrl } from './lib/mediaUrl';
import { msToTimecode } from './lib/projectAdapter';
import { buildCues, cueAt, sourceMsAt, opacityAt } from './lib/compilationCues';
import { TitleCardText } from './JoinerEditor';

const { useState, useEffect, useMemo, useRef, useCallback } = React;

// Play the compilation before it exists.
//
// The Inspector can play one scene and the strip under the canvas colours
// the whole thing by speed, but nothing could answer "what does the join
// at 41:12 actually look like" without a twenty-minute encode. This walks
// the cue list, swapping the video source at each scene boundary and
// drawing the joiner holds itself, so the joins and the title cards can
// be watched at the cost of a seek.
//
// It is a preview, not the render: it dims across fades rather than
// compositing them, and it does not mix audio across a join. What it is
// exact about is TIMING and ORDER — which scene, at which moment, from
// which point in its source.

export function CompilationPreview({ project, open, onToggle }) {
  const { cues, totalMs } = useMemo(
    () => buildCues(project, FA_DATA.joinerAddedMs),
    [project],
  );

  const [ms, setMs] = useState(0);
  const [playing, setPlaying] = useState(false);
  const videoRef = useRef(null);
  const trackRef = useRef(null);
  // The cue whose source is currently loaded, so we only touch `src` when
  // it actually changes. Re-assigning it every render would restart the
  // download and make playback stutter at best.
  const loadedRef = useRef(null);

  const cue = cueAt(cues, ms);

  // Past the end: stop rather than run off into nothing.
  useEffect(() => {
    if (playing && totalMs > 0 && ms >= totalMs) {
      setPlaying(false);
      setMs(totalMs);
    }
  }, [playing, ms, totalMs]);

  // ── Load and seek the source for the cue in flight ───────────────
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    if (!cue || cue.kind !== 'scene') {
      // A hold has no source. Pause rather than leaving the previous
      // scene running silently underneath the card.
      if (!v.paused) v.pause();
      return;
    }
    const wantSrc = toMediaUrl(cue.file);
    if (loadedRef.current !== cue.segId) {
      loadedRef.current = cue.segId;
      v.src = wantSrc;
      v.load();
    }
    const targetS = (sourceMsAt(cue, ms) || 0) / 1000;
    // Only seek when we are actually out of step. Writing currentTime on
    // every tick fights the element's own playback.
    if (Math.abs(v.currentTime - targetS) > 0.35) {
      try { v.currentTime = targetS; } catch { /* not seekable yet */ }
    }
    if (playing && v.paused) v.play().catch(() => { /* autoplay refused */ });
    if (!playing && !v.paused) v.pause();
  }, [cue, ms, playing]);

  // ── The scene clock: the video drives it ─────────────────────────
  // Throttled to ~10Hz. `timeupdate` is not a render trigger you want
  // unthrottled, and the element fires it on its own schedule.
  const lastTickRef = useRef(0);
  const onTimeUpdate = useCallback(() => {
    const v = videoRef.current;
    if (!v || !playing) return;
    const now = Date.now();
    if (now - lastTickRef.current < 100) return;
    lastTickRef.current = now;
    const c = cueAt(cues, ms);
    if (!c || c.kind !== 'scene') return;
    const intoSource = v.currentTime * 1000 - (c.sourceStartMs || 0);
    const next = c.startMs + Math.max(0, intoSource);
    // Past this scene's trim-out: hand over to whatever comes next
    // rather than letting the source play on into footage the
    // compilation does not include.
    setMs(next >= c.endMs ? c.endMs : next);
  }, [cues, ms, playing]);

  // ── The hold clock: nothing is playing, so we tick it ────────────
  useEffect(() => {
    if (!playing || !cue || cue.kind !== 'hold') return undefined;
    // Advance by real elapsed time, and keep `ms` OUT of the deps: with
    // it here the interval was torn down and rebuilt on every tick.
    // `cue` is a stable object from the memoized list for as long as the
    // hold is on screen, so this runs once per hold.
    let last = Date.now();
    const id = setInterval(() => {
      const now = Date.now();
      const dt = now - last;
      last = now;
      setMs(prev => Math.min(cue.endMs, prev + dt));
    }, 50);
    return () => clearInterval(id);
  }, [playing, cue]);

  // ── Scrubbing ────────────────────────────────────────────────────
  function seekFromEvent(e) {
    const el = trackRef.current;
    if (!el || totalMs <= 0) return;
    const r = el.getBoundingClientRect();
    const x = Math.max(0, Math.min(r.width, e.clientX - r.left));
    setMs(Math.round((x / r.width) * totalMs));
  }

  const pct = totalMs > 0 ? Math.max(0, Math.min(100, (ms / totalMs) * 100)) : 0;
  const holdColor = cue?.kind === 'hold' ? (cue.joiner?.color || '#000000') : null;
  const dim = cue ? opacityAt(cue, ms) : 1;

  if (!open) {
    return (
      <div style={{ padding: "6px 14px", borderTop: "1px solid var(--border)",
                    background: "var(--surface)", flexShrink: 0 }}>
        <Button kind="ghost" size="sm" icon="play" onClick={onToggle}
                 title="Play the compilation before forging it">
          Preview compilation
        </Button>
      </div>
    );
  }

  return (
    <div style={{ borderTop: "1px solid var(--border)", background: "var(--surface)",
                  padding: "10px 14px 12px", flexShrink: 0 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
        <Button kind="ghost" size="icon"
                 title={playing ? "Pause" : "Play the compilation"}
                 onClick={() => setPlaying(p => !p)}>
          <Icon name={playing ? "pause" : "play"} size={13} />
        </Button>
        <Button kind="ghost" size="icon" title="Back to the start"
                 onClick={() => { setMs(0); }}>
          <Icon name="skip-back" size={13} />
        </Button>
        <span className="mono" style={{ fontSize: 11.5, color: "var(--text)" }}>
          {msToTimecode(ms)}
        </span>
        <span className="mono" style={{ fontSize: 11, color: "var(--text-dim)" }}>
          / {msToTimecode(totalMs)}
        </span>
        <span style={{ flex: 1 }} />
        <span style={{ fontSize: 11, color: "var(--text-muted)",
                       overflow: "hidden", textOverflow: "ellipsis",
                       whiteSpace: "nowrap", maxWidth: 280 }}>
          {cue
            ? (cue.kind === 'hold'
                ? (cue.joiner?.kind === 'title_card' ? 'title card' : 'transition')
                : cue.title)
            : '—'}
        </span>
        <Button kind="ghost" size="sm" onClick={onToggle} title="Hide the preview">
          <Icon name="chevron-down" size={13} />
        </Button>
      </div>

      <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
        <div style={{
          position: "relative", width: 288, aspectRatio: "16 / 9", flexShrink: 0,
          background: "#000", borderRadius: 6, overflow: "hidden",
          border: "1px solid var(--border)",
        }}>
          <video
            ref={videoRef}
            muted
            playsInline
            onTimeUpdate={onTimeUpdate}
            style={{
              position: "absolute", inset: 0, width: "100%", height: "100%",
              objectFit: "contain",
              // The fades are not composited here; dimming is an honest
              // stand-in for "this is where the picture goes to black".
              opacity: cue?.kind === 'scene' ? dim : 0,
            }} />
          {cue?.kind === 'hold' && (
            <>
              <span style={{ position: "absolute", inset: 0, background: holdColor }} />
              {cue.joiner?.kind === 'title_card' && <TitleCardText joiner={cue.joiner} />}
            </>
          )}
          {!cue && (
            <div style={{ position: "absolute", inset: 0, display: "grid",
                          placeItems: "center", color: "var(--text-dim)",
                          fontSize: 11 }}>
              {cues.length ? "end of compilation" : "no scenes yet"}
            </div>
          )}
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          {/* Scrub track. Scene boundaries are ticks, holds are blocks, so
              the shape of the compilation is readable at a glance. */}
          <div ref={trackRef}
                onClick={seekFromEvent}
                style={{
                  position: "relative", height: 34, borderRadius: 5,
                  background: "var(--surface-2)", border: "1px solid var(--border)",
                  cursor: totalMs > 0 ? "pointer" : "default", overflow: "hidden",
                }}>
            {cues.map((c) => {
              const left = totalMs > 0 ? (c.startMs / totalMs) * 100 : 0;
              const w = totalMs > 0 ? ((c.endMs - c.startMs) / totalMs) * 100 : 0;
              const isHold = c.kind === 'hold';
              return (
                <span key={`${c.kind}-${c.startMs}`}
                      title={isHold
                        ? (c.joiner?.kind === 'title_card' ? 'title card' : 'transition')
                        : c.title}
                      style={{
                        position: "absolute", top: 0, bottom: 0,
                        left: `${left}%`, width: `${Math.max(w, 0.2)}%`,
                        background: isHold
                          ? (c.joiner?.color || '#000000')
                          : "rgba(255,140,66,0.22)",
                        borderLeft: "1px solid var(--border)",
                      }} />
              );
            })}
            <span style={{
              position: "absolute", top: 0, bottom: 0, left: `${pct}%`,
              width: 2, background: "var(--accent)", pointerEvents: "none",
            }} />
          </div>
          <div style={{ fontSize: 10.5, color: "var(--text-dim)", marginTop: 6,
                        lineHeight: 1.5 }}>
            Order and timing are exact. Fades are shown as dimming rather than
            composited, and audio is muted — this is the shape of the cut, not
            the render.
          </div>
        </div>
      </div>
    </div>
  );
}

export default CompilationPreview;
