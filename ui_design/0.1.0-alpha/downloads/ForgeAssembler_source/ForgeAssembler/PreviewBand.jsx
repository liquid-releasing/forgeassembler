// Sticky preview band — sits just above the Accept/Forge bar.
// Renders the heatmap (per-bin colour), beatmap (peak markers), and
// running totals. Click-to-seek-style hover line gives a sense of place.

const { useState: pbState } = React;

function PreviewBand({ project, totalMs, segCount }) {
  const [hover, setHover] = pbState(null); // 0..1 or null
  const ref = React.useRef();
  const bins = React.useMemo(() => FA_DATA.makeHeatmap(project), [project]);

  // Pick a velocity → color (mirrors the chart-vN gradient in the design system).
  function vColor(v) {
    if (v < 0.10) return "#1f3a8a";
    if (v < 0.25) return "#2563eb";
    if (v < 0.45) return "#06b6d4";
    if (v < 0.62) return "#22c55e";
    if (v < 0.78) return "#eab308";
    if (v < 0.90) return "#f97316";
    return "#ef4444";
  }

  // Beatmap peaks: synthetic peaks every 1/8th of timeline (4 phrases per chapter typical)
  const peakCount = Math.max(8, Math.round(totalMs / 12000));
  const peaks = Array.from({ length: peakCount }, (_, i) => {
    const t = (i + 0.5) / peakCount;
    return { t, intensity: 0.5 + 0.45 * Math.sin(i * 1.3) };
  });

  return (
    <div style={{
      background: "var(--surface)", borderTop: "1px solid var(--border)",
      padding: "12px 22px", flexShrink: 0,
      display: "flex", flexDirection: "column", gap: 10,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <span style={{ fontSize: 11.5, fontWeight: 700, color: "var(--text-dim)",
                       textTransform: "uppercase", letterSpacing: "0.1em" }}>
          Live preview
        </span>
        <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
          Heatmap and beatmap of the combined funscript — updated in-process, no render.
        </span>
        <div style={{ flex: 1 }} />
        <span className="mono" style={{ fontSize: 11, color: "var(--text-muted)" }}>
          total <strong style={{ color: "var(--text)" }}>{fmtTotal(totalMs)}</strong>
        </span>
        <span style={{ width: 1, height: 14, background: "var(--border)" }} />
        <span className="mono" style={{ fontSize: 11, color: "var(--text-muted)" }}>
          actions <strong style={{ color: "var(--text)" }}>{Math.round(totalMs / 50).toLocaleString()}</strong>
        </span>
        <span style={{ width: 1, height: 14, background: "var(--border)" }} />
        <span className="mono" style={{ fontSize: 11, color: "var(--text-muted)" }}>
          avg bpm <strong style={{ color: "var(--text)" }}>108</strong>
        </span>
        <span style={{ width: 1, height: 14, background: "var(--border)" }} />
        <span className="mono" style={{ fontSize: 11, color: "var(--text-muted)" }}>
          peak velocity <strong style={{ color: "#f97316" }}>0.82</strong>
        </span>
      </div>

      <div
        ref={ref}
        onMouseMove={(e) => {
          const r = ref.current.getBoundingClientRect();
          setHover(Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)));
        }}
        onMouseLeave={() => setHover(null)}
        style={{
          position: "relative", height: 56, borderRadius: 6,
          background: "var(--surface-2)", border: "1px solid var(--border)",
          overflow: "hidden", cursor: "crosshair",
        }}>
        {/* Heatmap: stacked vertical bars from baseline up */}
        <svg viewBox={`0 0 ${bins.length} 60`} preserveAspectRatio="none"
             style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}>
          {bins.map((b, i) => (
            <rect key={i}
                  x={i} y={60 - b.v * 56} width={1.05} height={b.v * 56}
                  fill={vColor(b.v)} opacity={0.85} />
          ))}
        </svg>

        {/* Beatmap: thin peak ticks along the bottom */}
        <svg viewBox="0 0 1 1" preserveAspectRatio="none"
             style={{ position: "absolute", left: 0, right: 0, bottom: 0,
                       width: "100%", height: 7, opacity: 0.9 }}>
          {peaks.map((p, i) => (
            <line key={i} x1={p.t} x2={p.t} y1={1 - p.intensity * 0.85} y2={1}
                  stroke="#fafafa" strokeWidth={0.004} opacity={0.65 + p.intensity * 0.35} />
          ))}
        </svg>

        {/* Section boundary marks */}
        <SectionBoundaries project={project} totalMs={totalMs} />

        {/* Hover cursor */}
        {hover != null && (
          <>
            <span style={{
              position: "absolute", top: 0, bottom: 0, left: `${hover * 100}%`,
              width: 1, background: "var(--text)", opacity: 0.9, pointerEvents: "none",
            }} />
            <span style={{
              position: "absolute", top: -22, left: `${hover * 100}%`,
              transform: "translateX(-50%)",
              padding: "1px 6px", background: "var(--bg)",
              border: "1px solid var(--border)",
              borderRadius: 3, fontFamily: "var(--font-mono)",
              fontSize: 10.5, color: "var(--text)", pointerEvents: "none",
              whiteSpace: "nowrap",
            }}>
              {fmtTotal(hover * totalMs)}
            </span>
          </>
        )}
      </div>

      {/* Channel readout */}
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span className="mono" style={{ fontSize: 10.5, color: "var(--text-dim)" }}>
          channels in output:
        </span>
        {(() => {
          // Detection-driven: any channel that appears on any clip.
          const flat = project.sections.flatMap(s => s.segments);
          const detected = FA_DATA.CHANNELS.filter(c => !c.future)
            .filter(c => flat.some(s => s.channels.includes(c.id)));
          return detected.map(c => (
            <span key={c.id} style={{
              display: "inline-flex", alignItems: "center", gap: 4,
              padding: "1px 7px", fontFamily: "var(--font-mono)",
              fontSize: 10, fontWeight: 600, letterSpacing: "0.04em",
              background: "rgba(62,213,152,0.08)", color: "#3ed598",
              border: "1px solid rgba(62,213,152,0.3)", borderRadius: 3,
            }}>
              <Icon name="check" size={9} /> {c.label}
            </span>
          ));
        })()}
        <div style={{ flex: 1 }} />
        <span className="mono" style={{ fontSize: 10.5, color: "var(--text-dim)" }}>
          beds active: {project.audioBeds.length}
        </span>
      </div>
    </div>
  );
}

function SectionBoundaries({ project, totalMs }) {
  let cursor = 0;
  const marks = [];
  for (const sec of project.sections) {
    if (cursor > 0) marks.push({ t: cursor / totalMs, color: sec.color });
    for (const seg of sec.segments) cursor += seg.durMs;
  }
  return (
    <>
      {marks.map((m, i) => (
        <span key={i} style={{
          position: "absolute", top: 0, bottom: 0, left: `${m.t * 100}%`,
          width: 2, background: m.color, opacity: 0.55, pointerEvents: "none",
        }} />
      ))}
    </>
  );
}

Object.assign(window, { PreviewBand });
