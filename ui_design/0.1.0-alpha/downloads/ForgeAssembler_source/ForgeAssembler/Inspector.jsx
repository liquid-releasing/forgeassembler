// Right inspector. Open when a clip is selected.
// Five tabs: Source · Audio · Overlays · Color · Funscript.
// When inspectorMode is "inline", this whole panel is hidden — the
// expanded clip-row InlineEditor takes its place.

const { useState: insState } = React;

function Inspector({ segs, bed, project, onClose, mode, onAddOverlay,
                     onBulkUpdate, onBulkDuplicate, onBulkRemove }) {
  if (mode === "inline") return null;
  if ((!segs || segs.length === 0) && !bed) return <InspectorEmpty />;
  if (bed) return <BedInspector bed={bed} project={project} onClose={onClose} />;
  if (segs.length === 1) {
    return <ClipInspector seg={segs[0]} onClose={onClose} onAddOverlay={onAddOverlay} />;
  }
  return <MultiSelectInspector segs={segs} onClose={onClose}
                                  onBulkUpdate={onBulkUpdate}
                                  onBulkDuplicate={onBulkDuplicate}
                                  onBulkRemove={onBulkRemove} />;
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
function ClipInspector({ seg, onClose, onAddOverlay }) {
  const [tab, setTab] = insState("source");
  const tabs = [
    { id: "source",   label: "Source",   icon: "film"          },
    { id: "audio",    label: "Audio",    icon: "music"         },
    { id: "overlays", label: "Overlays", icon: "layers"        },
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
        {tab === "source"   && <SourcePane seg={seg} />}
        {tab === "audio"    && <AudioPane seg={seg} />}
        {tab === "overlays" && <OverlaysPane seg={seg} onAddOverlay={onAddOverlay} />}
        {tab === "color"    && <ColorPane seg={seg} />}
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

function SourcePane({ seg }) {
  // Local playback simulation — drives the MediaViewer's playhead.
  // Real playback in the desktop app would route to whatever video
  // engine the host uses; here we tick a fake clock so the transport
  // buttons feel live in the prototype.
  const [currentMs, setCurrentMs] = insState(0);
  const [playing, setPlaying]     = insState(false);

  // Trim state — synthesised source duration is ~30% longer than the
  // effective duration so the scrubber always has headroom to expose.
  // The effective duration shown elsewhere = trimOutMs − trimInMs.
  const sourceDurMs = React.useMemo(() => seg.sourceDurMs ??
    Math.max(seg.durMs + 1500, Math.round(seg.durMs * 1.3)), [seg]);
  const [trim, setTrim] = insState(() => ({
    trimInMs: seg.trimInMs ?? Math.round((sourceDurMs - seg.durMs) / 2),
    trimOutMs: seg.trimOutMs ?? Math.round((sourceDurMs - seg.durMs) / 2) + seg.durMs,
  }));
  React.useEffect(() => {
    setCurrentMs(0); setPlaying(false);
    setTrim({
      trimInMs: seg.trimInMs ?? Math.round((sourceDurMs - seg.durMs) / 2),
      trimOutMs: seg.trimOutMs ?? Math.round((sourceDurMs - seg.durMs) / 2) + seg.durMs,
    });
  }, [seg.id]);

  React.useEffect(() => {
    if (!playing) return;
    let raf, last = performance.now();
    const tick = (now) => {
      const dt = now - last; last = now;
      setCurrentMs(t => {
        const next = t + dt;
        if (next >= sourceDurMs) { setPlaying(false); return sourceDurMs; }
        return next;
      });
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, sourceDurMs]);

  // Synthetic "chapter" for the MediaViewer's playhead — the chapter
  // span IS the trim window, so the baton's position reflects where
  // playback would be relative to the trimmed range.
  const chapter = { id: seg.id, title: seg.title, color: "#ff8c42",
                     start: trim.trimInMs, end: trim.trimOutMs };

  const effectiveMs = trim.trimOutMs - trim.trimInMs;

  return (
    <>
      <PaneSection title="Preview"
                    hint={seg.kind === "still"
                      ? "Still image — shown for its hold duration."
                      : "Video preview with frame-step transport."}>
        <window.MediaViewer
          currentMs={currentMs}
          isPlaying={playing}
          onPlayPause={() => setPlaying(p => !p)}
          onSeek={(ms) => setCurrentMs(Math.max(0, Math.min(sourceDurMs, ms)))}
          chapter={chapter}
          showCreateChapter={false}
          media={{ kind: seg.kind === "still" ? "audio" : "video", title: seg.title }}
          width="100%" height={180} />
      </PaneSection>

      <PaneSection title="File">
        <Field><TextInput value={seg.file} mono /></Field>
      </PaneSection>

      {seg.kind === "video" ? (
        <PaneSection title="Trim window"
                      hint="Drag the handles to set in / out. The dimmed regions are cut from the source.">
          <TrimScrubber sourceDurMs={sourceDurMs}
                          trimInMs={trim.trimInMs} trimOutMs={trim.trimOutMs}
                          currentMs={currentMs}
                          onChange={(t) => setTrim(t)}
                          onSeek={(ms) => setCurrentMs(ms)} />
        </PaneSection>
      ) : (
        <PaneSection title="Still duration"
                      hint="How long the image is held on screen.">
          <Slider value={seg.durMs / 1000} min={0.5} max={20} step={0.1}
                  onChange={() => {}} valueLabel={`${(seg.durMs / 1000).toFixed(1)}s`} />
        </PaneSection>
      )}

      <PaneSection title="Scaling"
                    hint="How this clip fills the project resolution.">
        <Segmented value="fit" onChange={() => {}}
                    options={[{ value: "fit", label: "Fit (bars)" }, { value: "fill", label: "Crop fill" }]} />
      </PaneSection>
    </>
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
  function fmt(ms) {
    const s = Math.max(0, ms / 1000);
    const m = Math.floor(s / 60);
    const sec = s - m * 60;
    return `${String(m).padStart(2, "0")}:${sec.toFixed(2).padStart(5, "0")}`;
  }
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

function AudioPane({ seg }) {
  return (
    <>
      <PaneSection title="Audio mode"
                    hint="Keep the source audio, replace with an external file, or go silent.">
        <Segmented value={seg.audio} onChange={() => {}}
                    options={[
                      { value: "keep", label: "Keep" },
                      { value: "replace", label: "Replace" },
                      { value: "silence", label: "Silence" },
                    ]} />
      </PaneSection>
      {seg.audio === "replace" && (
        <PaneSection title="Replacement file"
                      hint="Any audio format ffmpeg understands.">
          <Field><TextInput value={seg.audioFile || ""} mono /></Field>
        </PaneSection>
      )}
      <PaneSection title="Per-clip volume">
        <Slider value={0} min={-20} max={6} step={1}
                onChange={() => {}} valueLabel="0 dB" />
      </PaneSection>
      <PaneSection title="Cross-clip audio"
                    hint="Audio beds (set on the Build canvas) sit above per-clip audio and can duck or replace it across joiners.">
        <div style={{ padding: "8px 10px", border: "1px solid var(--border)",
                       background: "var(--surface-2)", borderRadius: 6,
                       fontSize: 11, color: "var(--text-muted)" }}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <Icon name="music-4" size={12} style={{ color: "var(--accent-warm)" }} />
            No bed covers this clip.
          </span>
          <Button kind="ghost" size="sm" style={{ marginTop: 8 }} icon="plus">Cover this clip with a bed</Button>
        </div>
      </PaneSection>
    </>
  );
}

function OverlaysPane({ seg, onAddOverlay }) {
  // Prefer the real overlays list if present; fall back to a synthetic
  // single row when only the counter is set (legacy data).
  const overlays = (seg.overlaysList && seg.overlaysList.length > 0)
    ? seg.overlaysList
    : (seg.overlays > 0
        ? [{ id: "ov-legacy", kind: "image", file: "logo-white-on-black.png",
              position: "bl", opacity: 1.0, fadeInS: 1.0, fadeOutS: 0, startS: 0 }]
        : []);
  return (
    <>
      <PaneSection title="Overlays"
                    hint="Image overlays (logos, lower-thirds) and title-card overlays authored in the title editor."
                    right={<Button kind="ghost" size="sm" icon="plus"
                                    onClick={() => onAddOverlay?.(seg.id)}>Title overlay</Button>}>
        {overlays.length === 0 ? (
          <div style={{ padding: "14px 12px", border: "1px dashed var(--border)",
                         borderRadius: 6, textAlign: "center", color: "var(--text-dim)", fontSize: 12 }}>
            No overlays on this clip.
            <div style={{ marginTop: 8 }}>
              <Button kind="secondary" size="sm" icon="type"
                       onClick={() => onAddOverlay?.(seg.id)}>Author a title overlay</Button>
            </div>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {overlays.map(o => (
              <div key={o.id} style={{
                background: "var(--surface-2)", border: "1px solid var(--border)",
                borderRadius: 6, padding: 10,
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                  {o.thumb ? (
                    <div style={{ width: 38, height: 22, borderRadius: 3, overflow: "hidden",
                                    background: "#000", border: "1px solid var(--border)",
                                    flexShrink: 0, position: "relative" }}>
                      <img src={o.thumb} alt="" style={{ position: "absolute", inset: 0,
                                                          width: "100%", height: "100%" }} />
                    </div>
                  ) : (
                    <Icon name={o.kind === "title" ? "type" : "image"} size={13}
                          style={{ color: "var(--text-muted)" }} />
                  )}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <span className="mono" style={{ fontSize: 11, color: "var(--text)",
                                                      overflow: "hidden", textOverflow: "ellipsis",
                                                      whiteSpace: "nowrap", display: "block" }}>
                      {o.file}
                    </span>
                    {o.title?.title && (
                      <span style={{ fontSize: 10, color: "var(--text-dim)" }}>
                        “{o.title.title}”{o.title.subtitle ? ` · ${o.title.subtitle}` : ""}
                      </span>
                    )}
                  </div>
                  <Button kind="ghost" size="icon"><Icon name="trash-2" size={12} /></Button>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                  <Field label="Position">
                    <span className="mono" style={{ fontSize: 11, color: "var(--text)" }}>
                      {o.position}
                    </span>
                  </Field>
                  <Field label="Opacity">
                    <span className="mono" style={{ fontSize: 11, color: "var(--text)" }}>
                      {Math.round((o.opacity ?? 1) * 100)}%
                    </span>
                  </Field>
                  <Field label="Start">
                    <span className="mono" style={{ fontSize: 11, color: "var(--text)" }}>
                      {(o.startS ?? 0).toFixed(1)}s
                    </span>
                  </Field>
                  <Field label="Fade">
                    <span className="mono" style={{ fontSize: 11, color: "var(--text)" }}>
                      in {(o.fadeInS ?? 0).toFixed(1)}s · out {(o.fadeOutS ?? 0).toFixed(1)}s
                    </span>
                  </Field>
                </div>
              </div>
            ))}
          </div>
        )}
      </PaneSection>
    </>
  );
}

function ColorPane({ seg }) {
  const kelvin = 6500 + seg.temp;
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
                    onChange={() => {}}
                    valueLabel={`${kelvin}K · ${seg.temp >= 0 ? "+" : ""}${seg.temp} from neutral`} />
          </div>
        </div>
        <Button kind="secondary" size="sm" icon="camera">Preview frame</Button>
      </PaneSection>
    </>
  );
}

function FunscriptPane({ seg }) {
  const detected = seg.channels;
  const all = FA_DATA.CHANNELS.filter(c => !c.future);
  return (
    <>
      <PaneSection title="Detected channels"
                    hint="ForgeAssembler scanned the folder beside the video and found these funscript files.">
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {all.map(c => {
            const has = detected.includes(c.id);
            return (
              <div key={c.id} style={{
                display: "flex", alignItems: "center", gap: 8,
                padding: "6px 8px", borderRadius: 5,
                background: has ? "rgba(62,213,152,0.06)" : "transparent",
                border: `1px solid ${has ? "rgba(62,213,152,0.25)" : "var(--border)"}`,
              }}>
                <Icon name={has ? "check" : "minus"} size={12}
                      style={{ color: has ? "var(--success)" : "var(--text-dim)" }} />
                <span style={{ fontSize: 12, fontWeight: 600, color: has ? "var(--text)" : "var(--text-dim)" }}>
                  {c.label}
                </span>
                <span className="mono" style={{ fontSize: 10, color: "var(--text-dim)", marginLeft: "auto" }}>
                  {c.desc}
                </span>
              </div>
            );
          })}
        </div>
      </PaneSection>
      <PaneSection title="Action count"
                    hint="From the main .funscript channel.">
        <div style={{ display: "flex", justifyContent: "space-between", padding: "8px 10px",
                       border: "1px solid var(--border)", background: "var(--surface-2)",
                       borderRadius: 6 }}>
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Total actions</span>
          <span className="mono" style={{ fontSize: 12, fontWeight: 600 }}>
            {detected.includes("main") ? Math.round(seg.durMs / 50) : "—"}
          </span>
        </div>
      </PaneSection>
    </>
  );
}

// ── Bed inspector (when an audio bed is selected) ─────────────────
function BedInspector({ bed, project, onClose }) {
  const flat = project.sections.flatMap(s => s.segments);
  const startSeg = flat.find(s => s.id === bed.startSegmentId);
  const endSeg = flat.find(s => s.id === bed.endSegmentId);
  return (
    <aside style={{
      width: "var(--inspector-w)", flexShrink: 0,
      background: "var(--surface)", borderLeft: "1px solid var(--border)",
      display: "flex", flexDirection: "column",
    }}>
      <div style={{ padding: "14px 14px 12px", borderBottom: "1px solid var(--border)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 40, height: 40, borderRadius: 6, flexShrink: 0,
            background: "linear-gradient(135deg, rgba(255,140,66,0.4), rgba(255,140,66,0.15))",
            border: "1px solid rgba(255,140,66,0.4)",
            display: "grid", placeItems: "center",
          }}>
            <Icon name="music-4" size={18} style={{ color: "var(--accent-warm)" }} />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 12.5, fontWeight: 600 }}>{bed.title}</div>
            <div className="mono" style={{ fontSize: 10.5, color: "var(--text-dim)",
                                            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {bed.file}
            </div>
          </div>
          <Button kind="ghost" size="icon" onClick={onClose}><Icon name="x" size={14} /></Button>
        </div>
      </div>

      <div style={{ flex: 1, minHeight: 0, overflow: "auto", padding: 14 }}>
        <PaneSection title="Coverage"
                      hint="Which clips this bed spans. The bed crossfades over joiners between covered clips.">
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <Field label="Starts at">
              <TextInput value={startSeg?.title || "—"} />
            </Field>
            <Field label="Ends at">
              <TextInput value={endSeg?.title || "—"} />
            </Field>
          </div>
        </PaneSection>

        <PaneSection title="Mix">
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <Slider value={bed.level} min={-30} max={0} step={1}
                    onChange={() => {}} label="Bed level"
                    valueLabel={`${bed.level} dB`} />
            <Slider value={bed.fadeInS} min={0} max={10} step={0.5}
                    onChange={() => {}} label="Fade in"
                    valueLabel={`${bed.fadeInS.toFixed(1)} s`} />
            <Slider value={bed.fadeOutS} min={0} max={10} step={0.5}
                    onChange={() => {}} label="Fade out"
                    valueLabel={`${bed.fadeOutS.toFixed(1)} s`} />
          </div>
        </PaneSection>

        <PaneSection title="Behaviour vs clip audio"
                      hint="What happens to each covered clip's own audio while the bed plays.">
          <Segmented value={bed.duckUnderSegmentAudio ? "duck" : "solo"} onChange={() => {}}
                      options={[
                        { value: "duck", label: "Duck under clips" },
                        { value: "solo", label: "Replace clips" },
                      ]} />
          <div style={{ marginTop: 8, fontSize: 11, color: "var(--text-muted)", lineHeight: 1.5 }}>
            {bed.duckUnderSegmentAudio
              ? "Clip audio drops to −12 dB while the bed plays. Joiners crossfade the bed over."
              : "Per-clip audio is muted under this bed's coverage. Joiners use the bed for continuity."}
          </div>
        </PaneSection>
      </div>
    </aside>
  );
}

// ── MultiSelectInspector ─────────────────────────────────────────
// Shown when more than one clip is selected. Surfaces the values that
// are common across the selection, marks mixed ones explicitly, and
// applies edits to every selected clip at once.
function MultiSelectInspector({ segs, onClose, onBulkUpdate, onBulkDuplicate, onBulkRemove }) {
  // ── Summaries ──
  const kinds = uniq(segs.map(s => s.kind));
  const audioModes = uniq(segs.map(s => s.audio));
  const temps = uniq(segs.map(s => s.temp));
  const allVideos = kinds.length === 1 && kinds[0] === "video";

  // Channel coverage across selection
  const allChannelIds = ["main","multi_axis","estim_3p","alt","audio_estim"];
  const channelCoverage = allChannelIds.map(id => ({
    id,
    label: window.FA_DATA?.CHANNELS?.find(c => c.id === id)?.label || id,
    have: segs.filter(s => s.channels.includes(id)).length,
    total: segs.length,
  })).filter(c => c.have > 0);

  // Section spread
  const sectionCounts = {};
  for (const s of segs) {
    const k = s._sectionId || "—"; // not threaded; visualised below by colour
  }

  const totalMs = segs.reduce((a, s) => a + s.durMs, 0);

  return (
    <aside style={{
      width: "var(--inspector-w)", flexShrink: 0, minWidth: 0,
      background: "var(--surface)", borderLeft: "1px solid var(--border)",
      display: "flex", flexDirection: "column",
    }}>
      {/* Header */}
      <div style={{ padding: "12px 14px", borderBottom: "1px solid var(--border)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 38, height: 38, borderRadius: 7, flexShrink: 0,
            background: "rgba(255,75,75,0.12)",
            border: "1px solid rgba(255,75,75,0.3)",
            display: "grid", placeItems: "center",
            color: "var(--accent-2)", fontWeight: 700, fontSize: 14,
            fontFamily: "var(--font-mono)",
          }}>{segs.length}</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 12.5, fontWeight: 600 }}>
              {segs.length} clips selected
            </div>
            <div className="mono" style={{ fontSize: 10.5, color: "var(--text-dim)", marginTop: 1 }}>
              {fmtTotal(totalMs)} total · {kinds.length === 1
                ? (kinds[0] === "still" ? "all stills" : "all videos")
                : `${segs.filter(s => s.kind === "video").length} videos · ${segs.filter(s => s.kind === "still").length} stills`}
            </div>
          </div>
          <Button kind="ghost" size="icon" onClick={onClose} title="Clear (Esc)"><Icon name="x" size={14} /></Button>
        </div>

        {/* Thumbnail pile */}
        <div style={{ display: "flex", gap: 4, marginTop: 10, flexWrap: "wrap" }}>
          {segs.slice(0, 9).map(s => (
            <span key={s.id} title={s.title}
                   style={{
                     width: 26, height: 15, borderRadius: 2, overflow: "hidden",
                     border: "1px solid var(--border)", flexShrink: 0,
                     background: "var(--surface-2)",
                   }}>
              <img src={s.thumb} alt="" style={{ width: "100%", height: "100%",
                                                    objectFit: "cover", display: "block" }} />
            </span>
          ))}
          {segs.length > 9 && (
            <span className="mono" style={{
              fontSize: 10, color: "var(--text-muted)",
              padding: "0 4px", alignSelf: "center",
            }}>+{segs.length - 9}</span>
          )}
        </div>

        {/* Quick actions */}
        <div style={{ display: "flex", gap: 6, marginTop: 12 }}>
          <Button kind="secondary" size="sm" icon="copy" onClick={onBulkDuplicate}>Duplicate</Button>
          <Button kind="secondary" size="sm" icon="scissors">Split…</Button>
          <div style={{ flex: 1 }} />
          <Button kind="danger" size="sm" icon="trash-2" onClick={onBulkRemove}>Remove</Button>
        </div>
      </div>

      {/* Body */}
      <div style={{ flex: 1, minHeight: 0, overflow: "auto", padding: 14 }}>

        {/* Audio mode */}
        <PaneSection title="Audio mode"
                      hint={audioModes.length === 1
                        ? `All ${segs.length} clips use “${audioModes[0]}”.`
                        : `Mixed — ${segs.length} clips use ${audioModes.length} different values. Pick one to apply to all.`}>
          <div style={{ display: "flex", gap: 4 }}>
            {[
              { v: "keep",    label: "Keep",    icon: "volume-2" },
              { v: "replace", label: "Replace", icon: "music" },
              { v: "silence", label: "Silence", icon: "volume-x" },
            ].map(opt => {
              const all = audioModes.length === 1 && audioModes[0] === opt.v;
              return (
                <button key={opt.v}
                         onClick={() => onBulkUpdate({ audio: opt.v })}
                         style={{
                           flex: 1, display: "flex", flexDirection: "column",
                           alignItems: "center", gap: 4,
                           padding: "8px 6px", borderRadius: 6,
                           background: all ? "rgba(255,75,75,0.08)" : "var(--surface-2)",
                           border: `1px solid ${all ? "var(--accent)" : "var(--border)"}`,
                           color: all ? "var(--text)" : "var(--text-muted)",
                           cursor: "pointer", fontFamily: "inherit",
                           fontSize: 11, fontWeight: 600,
                         }}>
                  <Icon name={opt.icon} size={14} />
                  <span>{opt.label}</span>
                </button>
              );
            })}
          </div>
          {audioModes.length > 1 && (
            <div className="mono" style={{ fontSize: 10.5, color: "var(--text-dim)", marginTop: 8 }}>
              currently: {audioModes.map(m =>
                `${m} (${segs.filter(s => s.audio === m).length})`).join(" · ")}
            </div>
          )}
        </PaneSection>

        {/* Color temperature — videos only */}
        {allVideos ? (
          <PaneSection title="Color temperature"
                        hint={temps.length === 1
                          ? `All clips: ${temps[0] === 0 ? "neutral" : (temps[0] >= 0 ? "+" : "") + temps[0] + "K"}.`
                          : `Mixed — ${temps.length} different values across selection.`}>
            <BulkTempControl segs={segs} onApply={(v) => onBulkUpdate({ temp: v })} />
          </PaneSection>
        ) : (
          <PaneSection title="Color temperature">
            <div style={{ padding: "8px 10px", fontSize: 11.5, color: "var(--text-dim)",
                            border: "1px solid var(--border)", borderRadius: 6,
                            background: "var(--surface-2)" }}>
              Selection includes still images — colour temperature only applies to video clips.
            </div>
          </PaneSection>
        )}

        {/* Channel coverage */}
        <PaneSection title="Funscript channels"
                      hint="Which channels are present across the selected clips.">
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {channelCoverage.length === 0 && (
              <div style={{ padding: "8px 10px", fontSize: 11.5, color: "var(--text-dim)",
                              border: "1px solid var(--border)", borderRadius: 6,
                              background: "var(--surface-2)" }}>
                None of the selected clips carries a funscript channel.
              </div>
            )}
            {channelCoverage.map(c => {
              const full = c.have === c.total;
              return (
                <div key={c.id} style={{
                  display: "flex", alignItems: "center", gap: 8,
                  padding: "5px 8px", borderRadius: 5,
                  background: full ? "rgba(62,213,152,0.06)" : "var(--surface-2)",
                  border: `1px solid ${full ? "rgba(62,213,152,0.25)" : "var(--border)"}`,
                }}>
                  <Icon name={full ? "check" : "alert-circle"} size={11}
                        style={{ color: full ? "var(--success)" : "var(--warn)" }} />
                  <span style={{ fontSize: 12, fontWeight: 600 }}>{c.label}</span>
                  <span className="mono" style={{ fontSize: 10.5, color: "var(--text-dim)", marginLeft: "auto" }}>
                    {c.have} / {c.total}
                  </span>
                </div>
              );
            })}
          </div>
        </PaneSection>

        {/* Bulk overlay add — disabled until a single anchor concept makes sense */}
        <PaneSection title="Overlay"
                      hint="To add a title overlay across many clips, do them one at a time — overlay timing is per-clip and benefits from individual review.">
          <Button kind="ghost" size="sm" icon="info" disabled>Bulk overlay (coming soon)</Button>
        </PaneSection>
      </div>
    </aside>
  );
}

// Small helper — values seen across an array, deduped.
function uniq(arr) {
  const seen = new Set();
  const out = [];
  for (const v of arr) { if (!seen.has(v)) { seen.add(v); out.push(v); } }
  return out;
}

function BulkTempControl({ segs, onApply }) {
  const temps = uniq(segs.map(s => s.temp));
  const initialKelvin = temps.length === 1 ? 6500 + temps[0] : 6500;
  const [kelvin, setKelvin] = insState(initialKelvin);
  insUseEffect(() => { setKelvin(initialKelvin); }, [initialKelvin]);
  const offset = kelvin - 6500;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <Slider value={kelvin} min={4000} max={10000} step={100}
              onChange={setKelvin}
              valueLabel={`${kelvin}K · ${offset >= 0 ? "+" : ""}${offset} from neutral`} />
      <div style={{ display: "flex", gap: 6 }}>
        <Button kind="secondary" size="sm" icon="check"
                 onClick={() => onApply(offset)}>
          Apply {offset >= 0 ? "+" : ""}{offset}K to {segs.length} clips
        </Button>
        <Button kind="ghost" size="sm" onClick={() => onApply(0)}>Reset</Button>
      </div>
    </div>
  );
}

// (insState was imported at the top of this file from React; alias
//  insUseEffect for completeness since we use both.)
const insUseEffect = React.useEffect;

Object.assign(window, { Inspector });
