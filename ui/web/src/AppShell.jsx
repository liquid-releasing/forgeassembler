/* @esm-converted */
import React from 'react';
import { Button, Icon, Pill } from './primitives';

// ForgeAssembler AppShell — TopBar / pipeline TabStrip / StatusBar / AcceptBar.
// Same structural pattern as FunscriptForge's AppShell, retuned for the
// Assembler pipeline (Project → Build → Channels → Output → Forge).
//
// Naming convention: every component attaches to window at the bottom
// with an `fa` prefix to avoid collisions if FunscriptForge primitives
// are ever loaded into the same page.

const { useState: faShState } = React;

// ── Project family glyph (anvil silhouette stand-in) ───────────────
function FAGlyph({ size = 28 }) {
  return (
    <div style={{
      width: size, height: size, background: "var(--accent)", borderRadius: 6,
      display: "grid", placeItems: "center", color: "#fff", fontWeight: 800,
      fontFamily: "var(--font-mono)", fontSize: Math.round(size * 0.5),
      letterSpacing: "-0.04em", flexShrink: 0,
    }}>FA</div>
  );
}

// ── TopBar ────────────────────────────────────────────────────────
function FATopBar({ project, totalMs, segCount, sectionCount,
                    savedPath, dirty, lastSavedAtMs,
                    onOpen, onSave, onNew }) {
  // "saved 2 min ago" / "saving…" / "unsaved changes" / "new project"
  const filename = savedPath ? savedPath.split("/").pop() : `${project.name}.forgeproject.json`;
  const subtitle = savedPath ? null : "unsaved";
  return (
    <header style={{
      height: "var(--header-h)", padding: "0 18px", flexShrink: 0,
      background: "var(--surface)", borderBottom: "1px solid var(--border)",
      display: "flex", alignItems: "center", gap: 14,
    }}>
      <FAGlyph />
      <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.2 }}>
        <span style={{ fontSize: 13, fontWeight: 600, display: "flex", alignItems: "center", gap: 6 }}>
          <span>{filename}</span>
          {subtitle && (
            <span style={{ fontSize: 10, fontWeight: 700, padding: "1px 6px",
                            borderRadius: 3, background: "rgba(255,140,66,0.12)",
                            color: "var(--accent-warm)",
                            textTransform: "uppercase", letterSpacing: "0.08em",
                            border: "1px solid rgba(255,140,66,0.3)" }}>{subtitle}</span>
          )}
          {savedPath && dirty && (
            <span style={{ fontSize: 10, fontWeight: 700, padding: "1px 6px",
                            borderRadius: 3, background: "rgba(255,181,71,0.12)",
                            color: "var(--warn)",
                            textTransform: "uppercase", letterSpacing: "0.08em",
                            border: "1px solid rgba(255,181,71,0.3)" }}>unsaved changes</span>
          )}
          {savedPath && !dirty && (
            <span style={{ fontSize: 10, fontWeight: 700, padding: "1px 6px",
                            borderRadius: 3, background: "rgba(62,213,152,0.10)",
                            color: "var(--success)",
                            textTransform: "uppercase", letterSpacing: "0.08em",
                            border: "1px solid rgba(62,213,152,0.25)" }}>saved</span>
          )}
        </span>
        <span className="mono" style={{ fontSize: 11, color: "var(--text-dim)" }}>
          {sectionCount} section{sectionCount === 1 ? "" : "s"} · {segCount} segments · {fmtTotal(totalMs)} total · {project.output.resolution}
          {lastSavedAtMs && <span style={{ marginLeft: 8 }}>· saved {fmtRelative(lastSavedAtMs)}</span>}
        </span>
      </div>
      <Pill tone="accent" dot>Alpha 0.2</Pill>

      <div style={{ flex: 1 }} />

      <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
        <Button kind="ghost" size="icon" title="Undo"><Icon name="undo-2" size={14} /></Button>
        <Button kind="ghost" size="icon" title="Redo"><Icon name="redo-2" size={14} /></Button>
        <div style={{ width: 1, height: 22, background: "var(--border)", margin: "0 6px" }} />
        <Button kind="ghost" size="sm" icon="file-plus" onClick={onNew}
                title="Start an empty project">New</Button>
        <Button kind="secondary" size="sm" icon="folder-open" onClick={onOpen}>Open project…</Button>
        <Button kind={dirty ? "primary" : "secondary"} size="sm" icon="save"
                onClick={onSave}
                title={savedPath
                  ? (dirty ? "Save changes" : "Already saved")
                  : "Save project as…"}>
          {savedPath
            ? (dirty ? "Save changes" : "Saved")
            : "Save as…"}
        </Button>
      </div>
    </header>
  );
}

function fmtRelative(ms) {
  const now = Date.now();
  const dt = Math.max(0, now - ms) / 1000; // seconds
  if (dt < 5)    return "just now";
  if (dt < 60)   return `${Math.round(dt)}s ago`;
  if (dt < 3600) return `${Math.round(dt / 60)} min ago`;
  return `${Math.round(dt / 3600)}h ago`;
}

// ── Pipeline tab strip ────────────────────────────────────────────
// Linear flow. "Build" is the rich tab — others are sketched.
const FA_TABS = [
  { id: "project",  label: "Project",  icon: "folder",        pipeline: "project"  },
  { id: "build",    label: "Build",    icon: "layout-grid",   pipeline: "build"    },
  { id: "output",   label: "Output",   icon: "sliders",       pipeline: "output"   },
  { id: "forge",    label: "Forge",    icon: "hammer",        pipeline: "forge"    },
];
const FA_UTILITY_TABS = [
  { id: "joiners",  label: "Joiners",  icon: "library",       pipeline: null       },
];

function FATabButton({ t, i, list, active, pipeline, onChange }) {
  const isActive = t.id === active;
  const accepted = t.pipeline ? pipeline[t.pipeline]?.accepted : false;
  const upstream = i === 0 ? null : list[i - 1];
  const upAccepted = !upstream || (!upstream.pipeline) || pipeline[upstream.pipeline]?.accepted;
  const notReady = !upAccepted && !isActive;
  return (
    <button key={t.id} onClick={() => onChange(t.id)} style={{
      display: "flex", alignItems: "center", gap: 8,
      padding: "12px 14px", border: "none",
      background: "transparent", cursor: "pointer",
      color: isActive ? "var(--text)" : (notReady ? "var(--text-dim)" : "var(--text-muted)"),
      fontFamily: "inherit", fontSize: 12.5, fontWeight: 600,
      borderBottom: `2px solid ${isActive ? "var(--accent)" : "transparent"}`,
      opacity: notReady ? 0.7 : 1, position: "relative",
    }}>
      <Icon name={t.icon} size={14} />
      <span>{t.label}</span>
      <span className="mono" style={{
        fontSize: 10, color: "var(--text-dim)", fontWeight: 500,
        marginLeft: 2, opacity: 0.7,
      }}>{i < FA_TABS.length ? String(i + 1).padStart(2, "0") : ""}</span>
      {accepted && <span style={{
        width: 6, height: 6, borderRadius: "50%", background: "var(--success)",
        boxShadow: "0 0 6px rgba(62,213,152,0.6)", marginLeft: 2,
      }} />}
    </button>
  );
}

function FATabStrip({ active, onChange, pipeline }) {
  return (
    <nav style={{
      display: "flex", alignItems: "stretch",
      background: "var(--surface)", borderBottom: "1px solid var(--border)",
      padding: "0 18px", gap: 2, flexShrink: 0, overflowX: "auto",
    }}>
      {FA_TABS.map((t, i) => <FATabButton key={t.id} t={t} i={i} list={FA_TABS} active={active} pipeline={pipeline} onChange={onChange} />)}
      <div style={{ flex: 1 }} />
      <div style={{ width: 1, background: "var(--border)", margin: "8px 8px" }} />
      {FA_UTILITY_TABS.map((t, i) => <FATabButton key={t.id} t={t} i={i} list={FA_UTILITY_TABS} active={active} pipeline={pipeline} onChange={onChange} />)}
    </nav>
  );
}

// ── StatusBar ─────────────────────────────────────────────────────
function FAStatusBar({ activeTab, chainFile, ffmpeg = "imageio-ffmpeg 5.1" }) {
  return (
    <footer style={{
      height: "var(--status-h)", padding: "0 14px", flexShrink: 0,
      background: "var(--surface)", borderTop: "1px solid var(--border)",
      display: "flex", alignItems: "center", gap: 14, fontSize: 11, color: "var(--text-dim)",
    }}>
      <span><Icon name="circle-check" size={11} style={{ verticalAlign: "-1px", color: "var(--success)", marginRight: 4 }} />Saved</span>
      <span className="mono">tab: {activeTab}</span>
      {chainFile && <span className="mono">→ {chainFile}</span>}
      <div style={{ flex: 1 }} />
      <span className="mono">{ffmpeg}</span>
      <span>ForgeAssembler v0.2.0-alpha</span>
    </footer>
  );
}

// ── AcceptBar — bottom of every pipeline tab ──────────────────────
function FAAcceptBar({ summary, chainFile, accepted, onAccept, onReset, primaryLabel = "Accept and chain" }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 14,
      padding: "12px 22px", background: "var(--surface)",
      borderTop: "1px solid var(--border)", flexShrink: 0,
    }}>
      <Icon name={accepted ? "circle-check-big" : "info"} size={16}
            style={{ color: accepted ? "var(--success)" : "var(--text-dim)" }} />
      <div style={{ flex: 1, display: "flex", flexDirection: "column", lineHeight: 1.3 }}>
        <span style={{ fontSize: 12, color: "var(--text)" }}>{summary}</span>
        {chainFile && (
          <span className="mono" style={{ fontSize: 11, color: "var(--text-dim)" }}>
            writes <span style={{ color: "#ff7b7b" }}>{chainFile}</span> · downstream tabs read this file
          </span>
        )}
      </div>
      {accepted && <Pill tone="success" dot>Accepted</Pill>}
      <Button kind="ghost" size="sm" onClick={onReset}>Reset</Button>
      <Button kind={accepted ? "secondary" : "primary"} icon={accepted ? "rotate-cw" : "check"}
              onClick={onAccept}>
        {accepted ? "Re-accept" : primaryLabel}
      </Button>
    </div>
  );
}

// ── Layout helpers ────────────────────────────────────────────────
function FATabBody({ children, padded = true, style = {} }) {
  return (
    <div style={{
      flex: 1, minHeight: 0, overflow: "auto",
      padding: padded ? "20px 24px 12px" : 0,
      background: "var(--bg)", ...style,
    }}>
      {children}
    </div>
  );
}

function FATabHeader({ title, subtitle, eyebrow, right }) {
  return (
    <div style={{ display: "flex", alignItems: "flex-end",
                  justifyContent: "space-between", gap: 16, marginBottom: 18 }}>
      <div>
        {eyebrow && <div style={{ fontSize: 10.5, fontWeight: 700, color: "var(--text-dim)",
                                  textTransform: "uppercase", letterSpacing: "0.1em",
                                  marginBottom: 6 }}>{eyebrow}</div>}
        <h2 style={{ fontSize: 22, fontWeight: 700, margin: 0, letterSpacing: "-0.01em" }}>{title}</h2>
        {subtitle && <div style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 6,
                                   maxWidth: 720, lineHeight: 1.5 }}>{subtitle}</div>}
      </div>
      {right}
    </div>
  );
}

function FASectionLabel({ children, right }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
                  fontSize: 10.5, fontWeight: 700, color: "var(--text-dim)",
                  textTransform: "uppercase", letterSpacing: "0.1em",
                  marginBottom: 10 }}>
      <span>{children}</span>
      {right}
    </div>
  );
}

// ── Time formatters ───────────────────────────────────────────────
function fmtTotal(ms) {
  const s = Math.max(0, Math.round(ms / 1000));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h) return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  return `${m}:${String(sec).padStart(2, "0")}`;
}
function fmtClipDur(ms) {
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  const s = Math.round(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

Object.assign(window, {
  FATopBar, FATabStrip, FAStatusBar, FAAcceptBar,
  FATabBody, FATabHeader, FASectionLabel, FAGlyph,
  FA_TABS, FA_UTILITY_TABS,
  fmtTotal, fmtClipDur,
});


export { FAAcceptBar, FAGlyph, FASectionLabel, FAStatusBar, FATabBody, FATabButton, FATabHeader, FATabStrip, FATopBar, FA_TABS, FA_UTILITY_TABS, fmtClipDur, fmtRelative, fmtTotal };
