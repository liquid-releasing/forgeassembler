/* @esm-converted */
import React from 'react';
import { FAGlyph } from './AppShell';
import { Button, Icon, Pill } from './primitives';

// ── Home / launcher ───────────────────────────────────────────────
// Replaces the old "Project" pipeline tab. Pre-pipeline landing: start a
// new compilation, open an existing .forgeproject.json, or reopen a recent
// one. When a project is already loaded (e.g. the demo sample, or work in
// progress), a "Continue" card jumps straight back into Build.
function HomeScreen({ recents = [], hasWork, projectName, segCount, sectionCount,
                      totalLabel, onNew, onOpen, onOpenRecent, onContinue,
                      onLoadSample }) {
  return (
    <div style={{
      flex: 1, minHeight: 0, overflow: "auto", background: "var(--bg)",
      display: "flex", justifyContent: "center", padding: "48px 24px",
    }}>
      <div style={{ width: "100%", maxWidth: 760, display: "flex", flexDirection: "column", gap: 28 }}>

        {/* Hero */}
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <FAGlyph size={88} />
          <div>
            <h1 style={{ margin: 0, fontSize: 26, fontWeight: 800, letterSpacing: "-0.02em" }}>
              ForgeAssembler
            </h1>
            <div style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 4 }}>
              Stitch finished scenes into one compilation — video, funscripts, and haptic-estim audio together.
            </div>
          </div>
          <div style={{ flex: 1 }} />
          <Pill tone="accent" dot>Alpha 0.2</Pill>
        </div>

        {/* Continue current work (only when a project is loaded with clips) */}
        {hasWork && (
          <button onClick={onContinue} style={{
            display: "flex", alignItems: "center", gap: 14, textAlign: "left",
            padding: "16px 18px", borderRadius: 10, cursor: "pointer",
            background: "var(--surface)", border: "1px solid var(--accent)",
            color: "var(--text)", fontFamily: "inherit",
          }}>
            <Icon name="play" size={20} style={{ color: "var(--accent)" }} />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 14, fontWeight: 700 }}>Continue — {projectName}</div>
              <div className="mono" style={{ fontSize: 11.5, color: "var(--text-dim)", marginTop: 2 }}>
                {sectionCount} section{sectionCount === 1 ? "" : "s"} · {segCount} clips · {totalLabel}
              </div>
            </div>
            <Icon name="arrow-right" size={16} style={{ color: "var(--text-dim)" }} />
          </button>
        )}

        {/* Primary actions */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
          <button onClick={onNew} style={cardBtn(true)}>
            <Icon name="file-plus" size={22} style={{ color: "var(--accent)" }} />
            <div style={{ fontSize: 14, fontWeight: 700, marginTop: 10 }}>New compilation</div>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 3 }}>
              Start empty, then add clips or .forge scenes.
            </div>
          </button>
          <button onClick={onOpen} style={cardBtn(false)}>
            <Icon name="folder-open" size={22} style={{ color: "var(--text-muted)" }} />
            <div style={{ fontSize: 14, fontWeight: 700, marginTop: 10 }}>Open project…</div>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 3 }}>
              Reopen a saved .forgeproject.json.
            </div>
          </button>
        </div>

        {/* Sample project — design reference, labelled as such. It used to
            BE the boot state, which meant every launch opened on a
            compilation the user never made, pointing at files that don't
            exist. Reachable on purpose is fine; arriving unannounced is not. */}
        {onLoadSample && (
          <button onClick={onLoadSample} style={{
            display: "flex", alignItems: "center", gap: 10, width: "100%",
            padding: "10px 14px", textAlign: "left", cursor: "pointer",
            background: "transparent", border: "1px dashed var(--border)",
            borderRadius: 8, fontFamily: "inherit", color: "var(--text-muted)",
          }}>
            <Icon name="flask-conical" size={15} />
            <span style={{ fontSize: 12.5, fontWeight: 600 }}>Load the sample compilation</span>
            <span style={{ fontSize: 11.5 }}>
              — 8 clips of placeholder data, to see the layout. Its files aren't real.
            </span>
          </button>
        )}

        {/* Recents */}
        <div>
          <div style={{ fontSize: 10.5, fontWeight: 700, color: "var(--text-dim)",
                         textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 10 }}>
            Recent projects
          </div>
          {recents.length === 0 ? (
            <div style={{ padding: "18px 16px", borderRadius: 8, fontSize: 12.5,
                           color: "var(--text-muted)", background: "var(--surface-2)",
                           border: "1px dashed var(--border)" }}>
              Nothing yet — projects you open or save show up here.
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {recents.map((r, i) => (
                <button key={r.path || i} onClick={() => onOpenRecent(r)} style={{
                  display: "flex", alignItems: "center", gap: 12, padding: "9px 12px",
                  background: "transparent", border: "1px solid var(--border)",
                  borderRadius: 6, color: "var(--text)", cursor: "pointer",
                  fontFamily: "inherit", textAlign: "left",
                }}>
                  <Icon name="file-json-2" size={14} style={{ color: "var(--text-muted)", flexShrink: 0 }} />
                  <span className="mono" style={{ fontSize: 12, fontWeight: 600, flex: 1,
                                                   overflow: "hidden", textOverflow: "ellipsis",
                                                   whiteSpace: "nowrap" }}>{r.name || baseName(r.path)}</span>
                  <span className="mono" style={{ fontSize: 11, color: "var(--text-dim)",
                                                   overflow: "hidden", textOverflow: "ellipsis",
                                                   whiteSpace: "nowrap", maxWidth: 280 }}>{dirOf(r.path)}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function cardBtn(accent) {
  return {
    display: "flex", flexDirection: "column", alignItems: "flex-start",
    padding: "18px 18px 20px", borderRadius: 10, cursor: "pointer",
    background: "var(--surface)", textAlign: "left", fontFamily: "inherit",
    color: "var(--text)",
    border: `1px solid ${accent ? "var(--accent)" : "var(--border)"}`,
  };
}
function baseName(p) { return (p || "").replace(/\\/g, "/").split("/").pop() || "project"; }
function dirOf(p) {
  const norm = (p || "").replace(/\\/g, "/");
  const i = norm.lastIndexOf("/");
  return i > 0 ? norm.slice(0, i) : "";
}

Object.assign(window, { HomeScreen });

export { HomeScreen };
