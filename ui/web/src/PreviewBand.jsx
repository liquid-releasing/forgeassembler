/* @esm-converted */
import React from 'react';
const { useMemo, useRef } = React;
import { fmtTotal } from './AppShell';
import { Section } from './TitleEditor';
import { FA_DATA } from './data';
import { Icon } from './primitives';
import { previewProject } from './api/forge';
import { segmentHasChannel, toForgeProject } from './lib/projectAdapter';

// Sticky preview band — sits just above the Accept/Forge bar.
//
// Describes the COMBINED funscript the forge would write: the backend runs
// the same layout + concat the real forge does and reports peak speed per
// time bucket, so the strip cannot drift from the output. It used to draw a
// sine wave from mock data with hardcoded totals beside it.

const { useState: pbState } = React;

// The gradient forgeassembler_core/heatmap.py paints into the .heatmap.png
// the forge writes, in pos-units/sec. Sharing the stops means the strip and
// the rendered heatmap agree about what "hot" looks like.
const SPEED_STOPS = [
  [0, [30, 30, 80]], [50, [30, 100, 180]], [120, [30, 180, 150]],
  [200, [120, 200, 30]], [300, [240, 200, 30]], [400, [240, 120, 30]],
  [600, [240, 30, 30]],
];

// Which gradient band a speed falls in. Runs of the same band become one
// polyline, so the stroke line is velocity-coloured without emitting a
// separate element per action.
function speedBand(speed) {
  const s = Math.max(0, speed || 0);
  for (let i = SPEED_STOPS.length - 1; i >= 0; i--) if (s >= SPEED_STOPS[i][0]) return i;
  return 0;
}

function speedColor(speed) {
  const s = Math.max(0, Math.min(SPEED_STOPS[SPEED_STOPS.length - 1][0], speed || 0));
  for (let i = 0; i < SPEED_STOPS.length - 1; i++) {
    const [s0, c0] = SPEED_STOPS[i];
    const [s1, c1] = SPEED_STOPS[i + 1];
    if (s <= s1) {
      const t = s1 > s0 ? (s - s0) / (s1 - s0) : 0;
      return `rgb(${c0.map((c, k) => Math.round(c + t * (c1[k] - c))).join(',')})`;
    }
  }
  return 'rgb(240,30,30)';
}

function PreviewBand({ project, totalMs, segCount }) {
  const [hover, setHover] = pbState(null); // 0..1 or null
  const ref = React.useRef();
  const [summary, setSummary] = pbState(null);
  const [pending, setPending] = pbState(false);
  const [note, setNote] = pbState(null);

  // Recompute when the project settles. Every run lays out and concatenates
  // the whole project, so a debounce keeps a burst of edits (dragging a trim
  // handle, say) from queuing one pass per frame.
  React.useEffect(() => {
    if (!segCount) { setSummary(null); setNote(null); return undefined; }
    let cancelled = false;
    setPending(true);
    const id = setTimeout(() => {
      previewProject(toForgeProject(project, { folder: project.output?.folder }))
        .then((res) => { if (!cancelled) { setSummary(res); setNote(null); setPending(false); } })
        .catch((e) => {
          if (cancelled) return;
          // Reading the combined track needs every clip's real duration, so
          // a missing file stops it. Say so in a line rather than falling
          // silently blank — the sample compilation's placeholder paths hit
          // this every time, and a blank strip looks broken. The detail
          // belongs to Forge validation, not to a strip under the timeline.
          const missing = /Could not determine duration of .*?['"]([^'"]+)['"]/.exec(String(e?.message || e));
          setNote(missing
            ? `Can't read the combined track — no media for ${missing[1].split(/[\/]/).pop()}.`
            : "Can't read the combined track for this project.");
          setSummary(null); setPending(false);
        });
    }, 450);
    return () => { cancelled = true; clearTimeout(id); };
  }, [project, segCount]);

  const bins = summary?.bins || [];

  // The joined funscript as drawn segments, grouped into runs of one colour
  // band. This IS the artifact being assembled, so seams at joins show up
  // where a heatmap only hinted at them.
  const strokeRuns = React.useMemo(() => {
    const pts = summary?.points || [];
    const total = summary?.duration_ms || 0;
    if (pts.length < 2 || !total) return [];
    const runs = [];
    let current = null;
    for (let i = 0; i < pts.length - 1; i++) {
      const [at0, pos0] = pts[i];
      const [at1, pos1] = pts[i + 1];
      const dt = at1 - at0;
      const speed = dt > 0 ? (Math.abs(pos1 - pos0) * 1000) / dt : 0;
      const band = speedBand(speed);
      if (!current || current.band !== band) {
        current = { band, color: speedColor(speed), pts: [[at0 / total, pos0]] };
        runs.push(current);
      }
      current.pts.push([at1 / total, pos1]);
    }
    return runs;
  }, [summary]);

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
          {note
            ? note
            : pending
            ? "Reading the combined funscript…"
            : summary
              ? `The joined ${summary.channel} track, velocity-coloured, with peak speed along the bottom — no render.`
              : "Add clips to see the combined funscript."}
        </span>
        <div style={{ flex: 1 }} />
        <span className="mono" style={{ fontSize: 11, color: "var(--text-muted)" }}>
          total <strong style={{ color: "var(--text)" }}>{fmtTotal(totalMs)}</strong>
        </span>
        <span style={{ width: 1, height: 14, background: "var(--border)" }} />
        <span className="mono" style={{ fontSize: 11, color: "var(--text-muted)" }}>
          actions <strong style={{ color: "var(--text)" }}>
            {summary ? summary.action_count.toLocaleString() : "—"}
          </strong>
        </span>
        <span style={{ width: 1, height: 14, background: "var(--border)" }} />
        <span className="mono" style={{ fontSize: 11, color: "var(--text-muted)" }}>
          avg bpm <strong style={{ color: "var(--text)" }}>{summary ? summary.avg_bpm : "—"}</strong>
        </span>
        <span style={{ width: 1, height: 14, background: "var(--border)" }} />
        <span className="mono" style={{ fontSize: 11, color: "var(--text-muted)" }}>
          peak speed <strong style={{ color: summary ? speedColor(summary.peak_speed) : "var(--text-dim)" }}>
            {summary ? `${summary.peak_speed}/s` : "—"}
          </strong>
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
          position: "relative", height: 84, borderRadius: 6,
          background: "var(--surface-2)", border: "1px solid var(--border)",
          overflow: "hidden", cursor: "crosshair",
        }}>
        {/* The joined funscript. Position maps to the full 0-100 domain, so a
            script that never reaches the rails visibly doesn't. */}
        <svg viewBox="0 0 1 100" preserveAspectRatio="none"
             style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}>
          {[0, 50, 100].map(r => (
            <line key={r} x1={0} x2={1} y1={100 - r} y2={100 - r}
                  stroke="var(--text-dim)" strokeWidth={0.3} opacity={0.18} />
          ))}
          {strokeRuns.map((run, i) => (
            <polyline key={i} fill="none" stroke={run.color}
                      strokeWidth={0.9} vectorEffect="non-scaling-stroke"
                      strokeLinejoin="round" strokeLinecap="round"
                      points={run.pts.map(([t, pos]) => `${t},${100 - pos}`).join(' ')} />
          ))}
        </svg>

        {/* Peak speed per bucket, as a slim lane along the bottom — the
            heatmap this strip used to be, demoted to context. */}
        <svg viewBox={`0 0 ${Math.max(1, bins.length)} 10`} preserveAspectRatio="none"
             style={{ position: "absolute", left: 0, right: 0, bottom: 0,
                       width: "100%", height: 10 }}>
          {bins.map((b, i) => (
            <rect key={i} x={i} y={10 - Math.max(0.6, b.v * 10)}
                  width={1.05} height={Math.max(0.6, b.v * 10)}
                  fill={speedColor(b.speed)} opacity={0.9} />
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
            .filter(c => flat.some(s => segmentHasChannel(s, c.id)));
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


export { PreviewBand, SectionBoundaries };
