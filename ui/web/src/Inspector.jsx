/* @esm-converted */
import React from 'react';
const { useEffect, useMemo, useRef } = React;
import { fmtClipDur, fmtTotal } from './AppShell';
import { ClipThumb } from './BuildTab';
import { MediaViewer, TrackStack } from 'forgemoment';
import { toMediaUrl } from './lib/mediaUrl';
import { pickFile, readSidecar } from './api/forge';
import { toAudioWaveform, toBeats, toFunscript } from './lib/sidecars';
import { channelGroup, CHANNEL_GROUPS, NEUTRAL_KELVIN,
         msToTimecode, timecodeToMs } from './lib/projectAdapter';
import { Button, Field, Icon, Segmented, Slider, TextInput } from './primitives';

// Right inspector. Open when a clip is selected.
// Five tabs: Source · Audio · Overlays · Color · Funscript.
// When inspectorMode is "inline", this whole panel is hidden — the
// scene row's pencil dialog takes its place.

const { useState: insState } = React;

// One scene at a time. The bed inspector went with cross-clip audio beds
// (nothing in the engine ever read them) and the multi-select inspector
// went with the multi-clip section, which no longer exists.
function Inspector({ segs, onClose, onUpdate }) {
  if (!segs || segs.length === 0) return <InspectorEmpty />;
  return <ClipInspector seg={segs[0]} onClose={onClose} onUpdate={onUpdate} />;
}

function InspectorEmpty() {
  return (
    <aside style={{
      width: "var(--inspector-w)", flexShrink: 0,
      background: "var(--surface)", borderLeft: "1px solid var(--border)",
      display: "flex", flexDirection: "column",
      alignItems: "center", justifyContent: "center", gap: 14,
      padding: 32, textAlign: "center",
    }}>
      <Icon name="mouse-pointer-square-dashed" size={32}
            style={{ color: "var(--text-dim)" }} />
      <div style={{ fontSize: 13, fontWeight: 600 }}>No clip selected</div>
      <div style={{ fontSize: 12, color: "var(--text-muted)", lineHeight: 1.5, maxWidth: 220 }}>
        Click any clip to edit its source, audio, overlays, color, and funscript channels.
      </div>
      <div style={{ height: 1, background: "var(--border)", width: "100%", margin: "12px 0" }} />
      <div style={{ fontSize: 11, color: "var(--text-dim)", lineHeight: 1.55 }}>
        <strong style={{ color: "var(--text-muted)" }}>Shift-click</strong> a second clip
        to select a range — or <strong style={{ color: "var(--text-muted)" }}>⌘ / Ctrl-click</strong>
        to add individual clips. Drag the grip handle to reorder.
      </div>
    </aside>
  );
}

// ── Clip inspector ────────────────────────────────────────────────
function ClipInspector({ seg, onClose, onUpdate }) {
  const [tab, setTab] = insState("source");
  // No Overlays tab: the only thing that added one was the title editor,
  // and titles are a later release. A project that already carries
  // overlays keeps them — the adapter passes them straight through.
  const tabs = [
    { id: "source",   label: "Source",   icon: "film"          },
    { id: "audio",    label: "Audio",    icon: "music"         },
    { id: "color",    label: "Color",    icon: "thermometer"   },
    { id: "fs",       label: "Funscript", icon: "activity"     },
  ];
  return (
    <aside style={{
      width: "var(--inspector-w)", flexShrink: 0, minWidth: 0,
      background: "var(--surface)", borderLeft: "1px solid var(--border)",
      display: "flex", flexDirection: "column",
    }}>
      {/* Header */}
      <div style={{ padding: "12px 14px", borderBottom: "1px solid var(--border)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <ClipThumb seg={seg} w={48} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--text)",
                          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {seg.title}
            </div>
            <div className="mono" style={{ fontSize: 10.5, color: "var(--text-dim)",
                                            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {seg.file}
            </div>
          </div>
          <Button kind="ghost" size="icon" onClick={onClose}><Icon name="x" size={14} /></Button>
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 10, fontSize: 11, color: "var(--text-muted)" }}>
          <span><strong className="mono" style={{ color: "var(--text)" }}>{fmtClipDur(seg.durMs)}</strong> duration</span>
          <span>·</span>
          <span>{seg.kind === "still" ? "Still image" : "Video clip"}</span>
        </div>
      </div>

      {/* Tab strip */}
      <div style={{ display: "flex", borderBottom: "1px solid var(--border)",
                    overflowX: "auto", flexShrink: 0 }}>
        {tabs.map(t => {
          const active = tab === t.id;
          return (
            <button key={t.id} onClick={() => setTab(t.id)} style={{
              display: "flex", alignItems: "center", gap: 5, flex: 1,
              padding: "10px 8px", border: "none", background: "transparent",
              cursor: "pointer", fontFamily: "inherit", fontSize: 11.5, fontWeight: 600,
              color: active ? "var(--text)" : "var(--text-muted)",
              borderBottom: `2px solid ${active ? "var(--accent)" : "transparent"}`,
              whiteSpace: "nowrap",
            }}>
              <Icon name={t.icon} size={12} />
              {t.label}
            </button>
          );
        })}
      </div>

      {/* Body */}
      <div style={{ flex: 1, minHeight: 0, overflow: "auto", padding: 14 }}>
        {tab === "source"   && <SourcePane seg={seg} onUpdate={onUpdate} />}
        {tab === "audio"    && <AudioPane seg={seg} onUpdate={onUpdate} />}
        {tab === "color"    && <ColorPane seg={seg} onUpdate={onUpdate} />}
        {tab === "fs"       && <FunscriptPane seg={seg} />}
      </div>
    </aside>
  );
}

// ── Tab panes ─────────────────────────────────────────────────────
function PaneSection({ title, hint, children, right }) {
  return (
    <section style={{ marginBottom: 18 }}>
      <div style={{ display: "flex", alignItems: "center", marginBottom: 8 }}>
        <span style={{ fontSize: 10.5, fontWeight: 700, color: "var(--text-dim)",
                       textTransform: "uppercase", letterSpacing: "0.1em" }}>{title}</span>
        <div style={{ flex: 1 }} />
        {right}
      </div>
      {hint && <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginBottom: 10, lineHeight: 1.5 }}>{hint}</div>}
      {children}
    </section>
  );
}

function SourcePane({ seg, onUpdate }) {
  // The video element is the master clock. forgemoment's MediaViewer
  // throttles its own timeupdate and gates seek echoes internally, so
  // currentMs can be written straight from onTimeChange.
  const [currentMs, setCurrentMs] = insState(0);
  const [playing, setPlaying]     = insState(false);

  const videoSrc = seg.kind === "still" || !seg.file ? null : toMediaUrl(seg.file);

  // The clip's real length. A `.forge` bundle reports it in its manifest and
  // loose clips get probed on add; there is no synthesised headroom, so the
  // trim window spans exactly what exists.
  const sourceDurMs = seg.sourceDurMs ?? seg.durMs ?? 0;
  const [trim, setTrim] = insState(() => ({
    trimInMs: seg.trimStartMs ?? 0,
    trimOutMs: seg.trimEndMs ?? sourceDurMs,
  }));
  React.useEffect(() => {
    setCurrentMs(seg.trimStartMs ?? 0);
    setPlaying(false);
    setTrim({ trimInMs: seg.trimStartMs ?? 0, trimOutMs: seg.trimEndMs ?? sourceDurMs });
  }, [seg.id, sourceDurMs]);

  // Analysis the bundle already carried — peaks, beats and the motion
  // track. Read when a clip is selected rather than at import: each peaks
  // sidecar is a few hundred KB and a compilation holds many clips.
  const [analysis, setAnalysis] = insState({ waveform: null, beats: null, funscript: null });
  React.useEffect(() => {
    let cancelled = false;
    setAnalysis({ waveform: null, beats: null, funscript: null });
    const sc = seg.sidecars || {};
    Promise.all([
      readSidecar(sc.audio), readSidecar(sc.beats),
      readSidecar((seg.explicitFunscripts || {}).main
                  || (seg.detectedFunscripts || {}).main),
    ]).then(([a, b, f]) => {
      if (cancelled) return;
      setAnalysis({ waveform: toAudioWaveform(a), beats: toBeats(b), funscript: toFunscript(f) });
    }).catch((e) => console.warn('[inspector] sidecars unavailable', e));
    return () => { cancelled = true; };
  }, [seg.id]);

  // Only tick a clock ourselves when there is no video to keep time —
  // a still, or a clip whose file hasn't resolved. With a video attached
  // the two clocks fight and the viewer's seek-sync snaps the picture back.
  React.useEffect(() => {
    if (!playing || videoSrc) return undefined;
    let raf, last = performance.now();
    const tick = (now) => {
      const dt = now - last; last = now;
      setCurrentMs((t) => {
        const next = t + dt;
        if (next >= sourceDurMs) { setPlaying(false); return sourceDurMs; }
        return next;
      });
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, videoSrc, sourceDurMs]);

  // Push a trim edit into the project. The view model names these
  // trimStartMs / trimEndMs; a window covering the whole clip means "no
  // trim", which is stored as null so the engine plays to the real end.
  function commitTrim(t) {
    setTrim(t);
    onUpdate?.({
      trimStartMs: t.trimInMs > 0 ? Math.round(t.trimInMs) : 0,
      trimEndMs: (sourceDurMs && t.trimOutMs >= sourceDurMs) ? null : Math.round(t.trimOutMs),
    });
  }

  const effectiveMs = trim.trimOutMs - trim.trimInMs;

  // The regions the trim throws away, as generic TrackStack spans, so the
  // overview shows what's being cut rather than only what's kept.
  const cutBands = [];
  if (trim.trimInMs > 0) {
    cutBands.push({ id: "cut-head", start: 0, end: trim.trimInMs,
                    color: "rgba(255,181,71,0.30)", label: "cut" });
  }
  if (sourceDurMs && trim.trimOutMs < sourceDurMs) {
    cutBands.push({ id: "cut-tail", start: trim.trimOutMs, end: sourceDurMs,
                    color: "rgba(255,181,71,0.30)", label: "cut" });
  }
  // Only ask for lanes that have something to show — TrackStack always
  // renders the events lane once it's listed, and an empty 16px band above
  // the picture is just noise.
  const sceneLanes = [
    ...(cutBands.length ? ["events"] : []),
    "funscript",
    ...(analysis.waveform ? ["audio"] : []),
  ];

  return (
    <>
      <PaneSection title="Preview"
                    hint={seg.kind === "still"
                      ? "Still image — shown for its hold duration."
                      : "Scrub to a cut point, then set it as the in or out."}>
      {/* Scene overview — the whole clip on one axis, above the picture and
          the same width as it. The video shows you WHERE YOU ARE; this shows
          you where that is IN THE SCENE, so you can jump straight to the last
          few seconds instead of scrubbing for them. Click anywhere to seek;
          the baton is the same clock as the player below. */}
      {videoSrc && sourceDurMs > 0 && (
        <div style={{ marginBottom: 10 }}>
          <TrackStack
            scope={{ start: 0, end: sourceDurMs }}
            actions={analysis.funscript?.actions || []}
            waveform={analysis.waveform}
            events={cutBands}
            lanes={sceneLanes}
            laneHeights={{ funscript: 64, audio: 34, events: 16 }}
            eventRows={1}
            currentMs={currentMs}
            onSeek={(ms) => setCurrentMs(Math.max(0, Math.min(sourceDurMs, ms)))}
            funscriptColorMode="velocity"
            baton="line"
            showRuler />
          <div style={{ display: "flex", justifyContent: "space-between",
                         marginTop: 4, fontSize: 10.5, color: "var(--text-dim)" }}>
            <span>{analysis.funscript ? "Whole scene — click to jump" : "No motion track in this bundle"}</span>
            {cutBands.length > 0 && (
              <span className="mono" style={{ color: "var(--warn)" }}>
                shaded = trimmed off
              </span>
            )}
          </div>
        </div>
      )}
        {videoSrc ? (
          <MediaViewer
            videoSrc={videoSrc}
            media={{ kind: "video", title: seg.title }}
            totalMs={sourceDurMs}
            currentMs={currentMs}
            isPlaying={playing}
            onPlayPause={() => setPlaying((p) => !p)}
            onSeek={(ms) => setCurrentMs(Math.max(0, Math.min(sourceDurMs, ms)))}
            onTimeChange={setCurrentMs}
            funscript={analysis.funscript}
            audioWaveform={analysis.waveform}
            beats={analysis.beats}
            hideEmptySpectro
            showMark={false}
            railGuides
            thumbnailAspect="16/9"
            controls={["back5", "frame-back", "play", "frame-forward", "forward5"]}
            modeToggleAlign="start"
            modeToggleSize="sm"
            showModeLabel={false} />
        ) : (
          <div style={{ padding: "18px 12px", textAlign: "center", fontSize: 11.5,
                        color: "var(--text-dim)", background: "var(--surface-2)",
                        border: "1px solid var(--border)", borderRadius: 8 }}>
            {seg.kind === "still" ? "Still image — nothing to scrub." : "No video file resolved for this clip."}
          </div>
        )}
        {seg.bundleLean && (
          <div style={{ fontSize: 11, color: "var(--warn)", marginTop: 8, lineHeight: 1.45 }}>
            This bundle carries no analysis — re-export it from FunscriptForge
            for a waveform and beats here.
          </div>
        )}
      </PaneSection>

      <PaneSection title="File">
        <Field><TextInput value={seg.file} mono /></Field>
      </PaneSection>

      {seg.kind === "video" ? (
        <PaneSection title="Trim window"
                      hint="Drag the handles to set in / out, or park the playhead and use the buttons. The dimmed regions are cut from the source.">
          <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
            <Button kind="secondary" size="sm" style={{ flex: 1 }}
                    onClick={() => commitTrim({ ...trim, trimInMs: Math.min(currentMs, trim.trimOutMs) })}>
              Set in
            </Button>
            <Button kind="secondary" size="sm" style={{ flex: 1 }}
                    onClick={() => commitTrim({ ...trim, trimOutMs: Math.max(currentMs, trim.trimInMs) })}>
              Set out
            </Button>
            <Button kind="ghost" size="sm"
                    title="Clear the trim — use the whole clip"
                    onClick={() => commitTrim({ trimInMs: 0, trimOutMs: sourceDurMs })}>
              Reset
            </Button>
          </div>
          <TrimScrubber sourceDurMs={sourceDurMs}
                          trimInMs={trim.trimInMs} trimOutMs={trim.trimOutMs}
                          currentMs={currentMs}
                          onChange={commitTrim}
                          onSeek={(ms) => setCurrentMs(ms)} />
          <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
            <div style={{ flex: 1 }}>
              <TimecodeField label="In" ms={trim.trimInMs}
                              minMs={0} maxMs={trim.trimOutMs}
                              title="hh:mm:ss.mmm — where this scene starts"
                              onCommit={(v) => commitTrim({ ...trim, trimInMs: v })} />
            </div>
            <div style={{ flex: 1 }}>
              <TimecodeField label="Out" ms={trim.trimOutMs}
                              minMs={trim.trimInMs} maxMs={sourceDurMs || undefined}
                              title="hh:mm:ss.mmm — where this scene ends"
                              onCommit={(v) => commitTrim({ ...trim, trimOutMs: v })} />
            </div>
          </div>
          <div className="mono" style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 8 }}>
            keeps {fmtClipDur(effectiveMs)} of {fmtClipDur(sourceDurMs)}
          </div>
        </PaneSection>
      ) : (
        <PaneSection title="Still duration"
                      hint="How long the image is held on screen.">
          <Slider value={seg.durMs / 1000} min={0.5} max={20} step={0.1}
                  onChange={(v) => onUpdate?.({ durMs: Math.round(v * 1000) })}
                  valueLabel={`${(seg.durMs / 1000).toFixed(1)}s`} />
        </PaneSection>
      )}
    </>
  );
}

// ── Timecode field ────────────────────────────────────────────────
// Type an exact in/out point as hh:mm:ss.mmm.
//
// Dragging a handle is fine for finding a moment and hopeless for
// landing on one: at a typical scrubber width a pixel is most of a
// second, so an exact cut was unreachable. hh:mm:ss.mmm is also the
// format the .forgeproject.json already stores trim_start / trim_end
// in, so what you type is what is written — no unit to translate and
// no rounding between the two.
//
// Commits on blur or Enter, never per keystroke: "00:0" is a state you
// pass through while typing, and committing it would fight you.
function TimecodeField({ label, ms, minMs = 0, maxMs, onCommit, title }) {
  const [draft, setDraft] = insState(() => msToTimecode(ms));
  const [bad, setBad] = insState(false);

  // Follow the value when it changes elsewhere — dragging a handle, Set
  // in/out, Reset — unless the user is mid-edit on a bad value.
  insUseEffect(() => { setDraft(msToTimecode(ms)); setBad(false); }, [ms]);

  function commit() {
    const parsed = timecodeToMs(draft);
    if (parsed == null) { setBad(true); return; }
    const clamped = Math.max(minMs, maxMs != null ? Math.min(parsed, maxMs) : parsed);
    setBad(false);
    setDraft(msToTimecode(clamped));
    onCommit(clamped);
  }

  return (
    <Field label={label}>
      <TextInput
        value={draft}
        mono
        title={title}
        onChange={(v) => { setDraft(v); if (bad) setBad(false); }}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") { commit(); e.currentTarget.blur(); }
          // Escape abandons the edit and shows the real value again.
          if (e.key === "Escape") { setDraft(msToTimecode(ms)); setBad(false); e.currentTarget.blur(); }
        }}
        style={bad ? { borderColor: "var(--danger)", color: "var(--danger)" } : undefined} />
    </Field>
  );
}

// ── Trim scrubber ─────────────────────────────────────────────────
// A horizontal source-duration track with two draggable handles bracketing
// the trim window. The MediaViewer's currentMs rides through as a thin
// vertical playhead. Click the track outside the handles to scrub.
function TrimScrubber({ sourceDurMs, trimInMs, trimOutMs, currentMs, onChange, onSeek }) {
  const trackRef = React.useRef();
  const [dragging, setDragging] = React.useState(null);

  function pct(ms) { return Math.max(0, Math.min(100, (ms / sourceDurMs) * 100)); }
  // Same units as the In/Out fields below the track. Two different time
  // formats on one control is how you misread one for the other.
  function fmt(ms) { return msToTimecode(ms); }
  function durFmt(ms) {
    const s = Math.max(0, Math.round(ms / 100) / 10);
    if (s < 60) return `${s.toFixed(1)}s`;
    const m = Math.floor(s / 60);
    const sec = Math.round(s - m * 60);
    return `${m}:${String(sec).padStart(2, "0")}`;
  }

  function startDrag(which) {
    return (e) => {
      e.preventDefault(); e.stopPropagation();
      const rect = trackRef.current.getBoundingClientRect();
      setDragging(which);
      function move(ev) {
        const p = Math.max(0, Math.min(1, (ev.clientX - rect.left) / rect.width));
        const newMs = Math.round(p * sourceDurMs);
        if (which === "in")  onChange({ trimInMs: Math.min(newMs, trimOutMs - 200), trimOutMs });
        else                  onChange({ trimInMs, trimOutMs: Math.max(newMs, trimInMs + 200) });
      }
      function up() {
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", up);
        setDragging(null);
      }
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up);
    };
  }

  function onTrackPointerDown(e) {
    if (e.target !== e.currentTarget) return;
    const rect = trackRef.current.getBoundingClientRect();
    const p = (e.clientX - rect.left) / rect.width;
    onSeek?.(Math.round(p * sourceDurMs));
  }

  const inPct  = pct(trimInMs);
  const outPct = pct(trimOutMs);
  const cur    = pct(currentMs);
  const effective = trimOutMs - trimInMs;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {/* Numeric readouts above the track */}
      <div style={{
        display: "flex", alignItems: "baseline", justifyContent: "space-between",
        fontFamily: "var(--font-mono)", fontSize: 11,
      }}>
        <span style={{ color: "var(--text-muted)" }}>
          in <span style={{ color: "var(--text)" }}>{fmt(trimInMs)}</span>
        </span>
        <span style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 1 }}>
          <span style={{ fontSize: 10.5, color: "var(--text-dim)", fontWeight: 700,
                          textTransform: "uppercase", letterSpacing: "0.08em" }}>used</span>
          <span style={{ fontSize: 13, fontWeight: 600, color: "var(--accent-warm)" }}>{durFmt(effective)}</span>
        </span>
        <span style={{ color: "var(--text-muted)" }}>
          out <span style={{ color: "var(--text)" }}>{fmt(trimOutMs)}</span>
        </span>
      </div>

      {/* The track */}
      <div ref={trackRef}
            onPointerDown={onTrackPointerDown}
            style={{
              position: "relative", height: 40,
              background: "var(--surface-2)",
              border: "1px solid var(--border)",
              borderRadius: 6, cursor: "crosshair",
              userSelect: "none", touchAction: "none",
            }}>
        {/* Dimmed before-trim and after-trim regions (cut from source) */}
        <span style={{
          position: "absolute", top: 0, bottom: 0, left: 0, width: `${inPct}%`,
          background: "rgba(0,0,0,0.45)",
          borderRight: "1px dashed rgba(255,255,255,0.08)",
          pointerEvents: "none",
        }} />
        <span style={{
          position: "absolute", top: 0, bottom: 0, left: `${outPct}%`, right: 0,
          background: "rgba(0,0,0,0.45)",
          borderLeft: "1px dashed rgba(255,255,255,0.08)",
          pointerEvents: "none",
        }} />

        {/* Selected trim band */}
        <span style={{
          position: "absolute", top: 0, bottom: 0,
          left: `${inPct}%`, width: `${outPct - inPct}%`,
          background: "linear-gradient(180deg, rgba(255,140,66,0.16), rgba(255,140,66,0.06))",
          borderTop: "1px solid rgba(255,140,66,0.35)",
          borderBottom: "1px solid rgba(255,140,66,0.35)",
          pointerEvents: "none",
        }} />

        {/* Faux thumbnail strip — six bands shown faintly behind the trim */}
        <svg viewBox="0 0 60 40" preserveAspectRatio="none" style={{
          position: "absolute", inset: 0, width: "100%", height: "100%",
          opacity: 0.18, pointerEvents: "none",
        }}>
          {Array.from({ length: 12 }, (_, i) => (
            <rect key={i} x={i * 5} y={2} width={4.5} height={36} fill="#fff" />
          ))}
        </svg>

        {/* Playhead */}
        <span style={{
          position: "absolute", top: -3, bottom: -3, left: `${cur}%`,
          width: 2, background: "#fafafa", borderRadius: 1,
          boxShadow: "0 0 4px rgba(250,250,250,0.5)",
          pointerEvents: "none", transform: "translateX(-50%)",
        }} />

        {/* In handle */}
        <Handle pos={inPct} dragging={dragging === "in"}
                 onPointerDown={startDrag("in")}
                 side="in" timecode={fmt(trimInMs)} />
        {/* Out handle */}
        <Handle pos={outPct} dragging={dragging === "out"}
                 onPointerDown={startDrag("out")}
                 side="out" timecode={fmt(trimOutMs)} />
      </div>

      {/* Source-duration footer */}
      <div style={{ display: "flex", alignItems: "center", gap: 6,
                     fontFamily: "var(--font-mono)", fontSize: 10.5,
                     color: "var(--text-dim)" }}>
        <span>0:00.00</span>
        <span style={{ flex: 1 }} />
        <span>source duration · <span style={{ color: "var(--text-muted)" }}>{fmt(sourceDurMs)}</span></span>
        <span style={{ flex: 1 }} />
        <span>{fmt(sourceDurMs)}</span>
      </div>
    </div>
  );
}

function Handle({ pos, dragging, onPointerDown, side, timecode }) {
  const [hover, setHover] = React.useState(false);
  const showTip = hover || dragging;
  return (
    <span
      onPointerDown={onPointerDown}
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{
        position: "absolute", top: -4, bottom: -4,
        left: `${pos}%`, width: 14, transform: "translateX(-50%)",
        cursor: "ew-resize", touchAction: "none",
        display: "flex", alignItems: "center", justifyContent: "center",
        zIndex: 3,
      }}>
      {/* The visual bar */}
      <span style={{
        width: 3, height: "100%", borderRadius: 2,
        background: dragging ? "var(--accent)" : "var(--accent-warm)",
        boxShadow: dragging
          ? "0 0 0 2px rgba(255,75,75,0.25), 0 0 10px rgba(255,75,75,0.5)"
          : "0 0 0 1px rgba(255,140,66,0.35)",
        transition: "background 80ms, box-shadow 80ms",
      }} />
      {/* Grab dot */}
      <span style={{
        position: "absolute",
        top: side === "in" ? -8 : "auto", bottom: side === "out" ? -8 : "auto",
        width: 12, height: 12, borderRadius: "50%",
        background: dragging ? "var(--accent)" : "var(--accent-warm)",
        border: "2px solid var(--surface)",
        boxShadow: "0 1px 3px rgba(0,0,0,0.4)",
        pointerEvents: "none",
      }} />
      {/* Tooltip */}
      {showTip && (
        <span style={{
          position: "absolute", top: -28,
          padding: "2px 6px", borderRadius: 3,
          background: "var(--bg)", border: "1px solid var(--border)",
          fontFamily: "var(--font-mono)", fontSize: 10.5,
          color: "var(--text)", whiteSpace: "nowrap",
          pointerEvents: "none",
        }}>
          {side === "in" ? "↦ " : "↤ "}{timecode}
        </span>
      )}
    </span>
  );
}

function AudioPane({ seg, onUpdate }) {
  async function pickReplacement() {
    const f = await pickFile({
      title: "Choose the replacement audio for this clip",
      filterName: "Audio", extensions: ["mp3", "wav", "m4a", "aac", "flac", "ogg", "opus"],
    });
    if (f) onUpdate?.({ audio: "replace", audioFile: f });
  }
  const needsFile = seg.audio === "replace" && !seg.audioFile;
  return (
    <>
      <PaneSection title="Audio mode"
                    hint="Keep the source audio, replace with an external file, or go silent.">
        <Segmented value={seg.audio}
                    onChange={(v) => onUpdate?.({ audio: v })}
                    options={[
                      { value: "keep", label: "Keep" },
                      { value: "replace", label: "Replace" },
                      { value: "silence", label: "Silence" },
                    ]} />
      </PaneSection>
      {seg.audio === "replace" && (
        <PaneSection title="Replacement file"
                      hint="Any audio format ffmpeg understands. It's stretched to nothing — if it's shorter than the clip, the rest is silent.">
          <Field>
            <TextInput value={seg.audioFile || ""} mono
                        placeholder="No file chosen" readOnly />
          </Field>
          <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
            <Button kind="secondary" size="sm" icon="folder-open"
                     onClick={pickReplacement}>Choose file…</Button>
            {seg.audioFile && (
              <Button kind="ghost" size="sm"
                       onClick={() => onUpdate?.({ audioFile: null })}>Clear</Button>
            )}
          </div>
          {needsFile && (
            <div style={{ fontSize: 11, color: "var(--warn)", marginTop: 8, lineHeight: 1.45 }}>
              Replace mode with no file fails validation — pick one, or switch back to Keep.
            </div>
          )}
        </PaneSection>
      )}
    </>
  );
}

// Colour temperature. The slider works in ABSOLUTE Kelvin because that's
// what a colourist thinks in and what ffmpeg takes; the view model stores
// the offset from neutral, and projectAdapter converts at the file
// boundary. 6500 K is neutral and writes no filter at all.
function ColorPane({ seg, onUpdate }) {
  const kelvin = NEUTRAL_KELVIN + seg.temp;
  const swatch = kelvin < 6000 ? "#cce4ff" : kelvin > 7000 ? "#ffd9a8" : "#fafafa";
  return (
    <>
      <PaneSection title="Color temperature"
                    hint="Nudge this clip warmer or cooler to match its neighbours. No global auto-match — that's a colorist's job.">
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 10 }}>
          <span style={{ width: 32, height: 32, borderRadius: 16, background: swatch,
                          border: "1px solid var(--border)" }} />
          <div style={{ flex: 1 }}>
            <Slider value={kelvin} min={4000} max={10000} step={100}
                    onChange={(v) => onUpdate?.({ temp: Math.round(v) - NEUTRAL_KELVIN })}
                    valueLabel={`${kelvin}K · ${seg.temp >= 0 ? "+" : ""}${seg.temp} from neutral`} />
          </div>
        </div>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <Button kind="ghost" size="sm" onClick={() => onUpdate?.({ temp: 0 })}
                   disabled={seg.temp === 0}>Reset to neutral</Button>
          <span style={{ fontSize: 11, color: "var(--text-dim)" }}>
            {seg.temp === 0
              ? "Neutral — this clip is passed through untouched."
              : "Applied when the video is forged."}
          </span>
        </div>
      </PaneSection>
    </>
  );
}

// What this clip actually contributes to the combined funscript. Reads
// the clip's REAL channel names — a FunscriptForge scene carries ~20,
// most of them device and restim-parameter tracks that no fixed menu
// lists. The old version checked `channels.includes(uiCategoryId)`, which
// only ever matched "main", so a 20-channel scene reported one.
function FunscriptPane({ seg }) {
  const detected = seg.channels || [];
  const byGroup = new Map();
  for (const ch of [...detected].sort()) {
    const g = channelGroup(ch);
    if (!byGroup.has(g)) byGroup.set(g, []);
    byGroup.get(g).push(ch);
  }
  const groups = CHANNEL_GROUPS.filter(g => byGroup.has(g.id));
  const source = seg.funscriptsSource === "explicit"
    ? "From the .forge bundle this clip was imported from."
    : "Scanned from the folder beside the video.";

  return (
    <>
      <PaneSection title={`Channels (${detected.length})`} hint={source}>
        {detected.length === 0 ? (
          <div style={{ padding: "12px 10px", borderRadius: 6, fontSize: 11.5,
                         color: "var(--text-dim)", background: "var(--surface-2)",
                         border: "1px dashed var(--border)", lineHeight: 1.5 }}>
            {seg.kind === "still"
              ? "Title cards carry no funscript — this clip is silent by design, and the other channels hold their last position across it."
              : "No funscript found for this clip. Wherever the other clips have channels, this stretch of the combined script will be blank."}
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {groups.map(g => (
              <div key={g.id}>
                <div className="mono" style={{ fontSize: 10, color: "var(--text-dim)",
                                                 textTransform: "uppercase",
                                                 letterSpacing: "0.06em", fontWeight: 700,
                                                 marginBottom: 4 }}>
                  {g.label}
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                  {byGroup.get(g.id).map(ch => (
                    <span key={ch} className="mono" style={{
                      fontSize: 10.5, padding: "2px 7px", borderRadius: 5,
                      background: "rgba(62,213,152,0.08)",
                      border: "1px solid rgba(62,213,152,0.25)",
                      color: "var(--text)",
                    }}>{ch}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </PaneSection>

      {seg.bundleLean && (
        <PaneSection title="Analysis">
          <div style={{ fontSize: 11.5, color: "var(--text-muted)", lineHeight: 1.5 }}>
            This bundle shipped no analysis sidecars, so previews derive the waveform
            from the video instead of reading it. The forged output is identical either way.
          </div>
        </PaneSection>
      )}
    </>
  );
}

// (insState was imported at the top of this file from React; alias
//  insUseEffect for completeness since we use both.)
const insUseEffect = React.useEffect;

Object.assign(window, { Inspector });


export { AudioPane, ClipInspector, ColorPane, FunscriptPane, Handle, Inspector,
         InspectorEmpty, PaneSection, SourcePane, TrimScrubber, insUseEffect };
