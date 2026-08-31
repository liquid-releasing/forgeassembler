/* @esm-converted */
import React from 'react';
import { FASectionLabel, FATabHeader, fmtClipDur, fmtTotal } from './AppShell';
import { Inspector } from './Inspector';
import { Section } from './TitleEditor';
import { FA_DATA } from './data';
import { DropLine, useDraggable, useDroppable } from './dragdrop';
import { Button, Field, Icon, Pill, Slider, TextInput } from './primitives';
import { toMediaUrl } from './lib/mediaUrl';

// ForgeAssembler — Build tab.
// Renders the active project as clips you can sequence + a cross-clip
// audio-bed lane spanning multiple segments.
//
// Layouts (driven by tweak `buildLayout`):
//   "sections"  — sections-grouped clip rows, joiners between sections (default)
//   "flat"      — single flat list of clip rows, joiners between every clip
//   "timeline"  — horizontal filmstrip of clip cards, joiners as gaps
//
// Joiner treatments (tweak `joinerStyle`):
//   "inline-pill"   — a tappable pill straddling the row gap (default, novel)
//   "divider"       — a thin labelled divider line
//   "lane"          — joiners live in a parallel left lane
//
// Density (`density`): "compact" | "comfortable" | "roomy".
// Inspector (`inspectorMode`): "right" panel or "inline" expansion.

const { useState: bsState, useRef: bsRef, useEffect: bsUseEffect } = React;

// ── Density tokens ────────────────────────────────────────────────
const DENSITY = {
  compact:     { thumb: 56,  rowPad: "8px 10px",  gap: 6,  font: 12.5, sub: 11 },
  comfortable: { thumb: 76,  rowPad: "12px 14px", gap: 10, font: 13,   sub: 11.5 },
  roomy:       { thumb: 104, rowPad: "18px 20px", gap: 14, font: 14,   sub: 12 },
};

// ── Channel chip ──────────────────────────────────────────────────
function ChannelChip({ id }) {
  const meta = (FA_DATA.CHANNELS.find(c => c.id === id) || {});
  const color = {
    main: "#ff7b7b", multi_axis: "#4dabf7", estim_3p: "#3ed598",
    estim_4p: "#3ed598", alt: "#ffb547", audio_estim: "#ff8c42", pulse_freq: "#9ba3c4",
  }[id] || "var(--text-muted)";
  const short = {
    main: "main", multi_axis: "m-ax", estim_3p: "estim", estim_4p: "estim4",
    alt: "alt", audio_estim: "wav", pulse_freq: "pulse",
  }[id] || id;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      padding: "1px 6px", borderRadius: 3, fontSize: 10, fontWeight: 600,
      fontFamily: "var(--font-mono)", letterSpacing: "0.02em",
      background: `${color}22`, color, border: `1px solid ${color}44`,
    }} title={meta.label}>{short}</span>
  );
}

// ── Device pills ──────────────────────────────────────────────────
// Collapse a segment's raw funscript channels into the device categories they
// drive, so a 15-channel scene reads as "Stroke · E-Stim ×14" instead of a
// long technical list. Hover a pill to see the underlying channels.
const _MULTI_AXIS = new Set(["surge", "sway", "twist", "roll", "pitch"]);
const _DEVICE_META = {
  stroke:    { label: "Stroke",     color: "#ff7b7b" },
  multiaxis: { label: "Multi-axis", color: "#4dabf7" },
  estim:     { label: "E-Stim",     color: "#3ed598" },
};
function bucketChannels(channels) {
  const g = { stroke: [], multiaxis: [], estim: [] };
  for (const c of channels || []) {
    if (c === "main") g.stroke.push(c);
    else if (_MULTI_AXIS.has(c)) g.multiaxis.push(c);
    else g.estim.push(c);
  }
  return g;
}
function DevicePills({ channels = [] }) {
  if (!channels.length)
    return <span style={{ fontSize: 10.5, color: "var(--text-dim)", fontFamily: "var(--font-mono)" }}>—</span>;
  const g = bucketChannels(channels);
  return (
    <>
      {["stroke", "multiaxis", "estim"].filter(k => g[k].length).map(k => {
        const m = _DEVICE_META[k];
        const list = g[k];
        return (
          <span key={k} title={list.join(", ")} style={{
            display: "inline-flex", alignItems: "center", gap: 4,
            padding: "1px 8px", borderRadius: 4, fontSize: 10.5, fontWeight: 600,
            fontFamily: "var(--font-mono)", letterSpacing: "0.02em",
            background: `${m.color}22`, color: m.color, border: `1px solid ${m.color}44`,
          }}>
            {m.label}{list.length > 1 ? ` ×${list.length}` : ""}
          </span>
        );
      })}
    </>
  );
}

// ── Audio mode glyph ──────────────────────────────────────────────
function AudioModeBadge({ mode }) {
  const map = {
    keep:    { icon: "volume-2",    label: "Keep",    color: "var(--text-muted)" },
    replace: { icon: "music",       label: "Replace", color: "#4dabf7" },
    silence: { icon: "volume-x",    label: "Silence", color: "var(--text-dim)" },
  };
  const m = map[mode] || map.keep;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      fontSize: 11, color: m.color,
    }} title={`Audio: ${m.label}`}>
      <Icon name={m.icon} size={12} />
      <span className="mono">{m.label.toLowerCase()}</span>
    </span>
  );
}

// ── Clip thumbnail with overlays ──────────────────────────────────
// What to draw when a clip has no thumbnail. Clips added from disk arrive
// without one — detection reports paths, not pictures — and an <img> with
// no src renders as the browser's broken-image glyph, which reads as an
// error rather than as "no preview yet".
const KIND_ICON = { video: "film", still: "image", audio: "audio-lines" };

function ClipThumb({ seg, w }) {
  const h = Math.round(w * 9 / 16);
  const isTitle = !!seg.titleCard;
  // A `.forge` bundle ships its own hero still; the adapter records the
  // path and it becomes an asset URL here (the adapter stays pure, with no
  // Tauri import, so it can be unit-tested).
  const src = seg.thumb || (seg.thumbPath ? toMediaUrl(seg.thumbPath) : null);
  return (
    <div style={{
      position: "relative", width: w, height: h, flexShrink: 0,
      borderRadius: 6, overflow: "hidden", background: "var(--surface-2)",
      border: "1px solid var(--border)",
    }}>
      {src ? (
        <img src={src} alt="" style={{ width: "100%", height: "100%", display: "block", objectFit: "cover" }} />
      ) : (
        <div style={{ width: "100%", height: "100%", display: "grid", placeItems: "center",
                      color: "var(--text-dim)" }}>
          <Icon name={isTitle ? "type" : (KIND_ICON[seg.kind] || "film")}
                size={Math.max(14, Math.round(h * 0.44))} stroke={1.5} />
        </div>
      )}
      {/* still-image badge */}
      {seg.kind === "still" && (
        <span style={{
          position: "absolute", top: 4, left: 4, padding: "1px 5px",
          background: "rgba(0,0,0,0.7)", color: "#fff", fontFamily: "var(--font-mono)",
          fontSize: 9, fontWeight: 700, letterSpacing: "0.06em",
          borderRadius: 2, lineHeight: 1.3,
        }}>{isTitle ? "TITLE" : "STILL"}</span>
      )}
      {/* duration badge */}
      <span style={{
        position: "absolute", bottom: 4, right: 4, padding: "1px 5px",
        background: "rgba(0,0,0,0.7)", color: "#fff", fontFamily: "var(--font-mono)",
        fontSize: 10, fontWeight: 600, borderRadius: 2,
      }}>{fmtClipDur(seg.durMs)}</span>
      {/* overlay dot */}
      {seg.overlays > 0 && (
        <span style={{
          position: "absolute", top: 4, right: 4, width: 6, height: 6,
          borderRadius: "50%", background: "var(--accent-warm)",
          boxShadow: "0 0 4px var(--accent-warm)",
        }} title={`${seg.overlays} overlay${seg.overlays === 1 ? "" : "s"}`} />
      )}
    </div>
  );
}

// ── Clip row (used by sections + flat layouts) ─────────────────────
function ClipRow({ seg, sectionColor, sectionId, density, selected, onSelect, expanded, onToggleExpand, inspectorMode, isStillRow, onEditClip }) {
  const d = DENSITY[density];
  const [hover, setHover] = bsState(false);
  const dragHandle = useDraggable({ kind: "clip", id: seg.id, fromSectionId: sectionId });
  const drop = useDroppable({ accept: "clip", id: seg.id, sectionId });
  return (
    <>
      <DropLine on={drop.hoverPosition === "before"} />
      <div
        ref={drop.ref}
        {...drop.handlers}
        onClick={(e) => onSelect(e)}
        onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
        style={{
          display: "flex", alignItems: "center", gap: d.gap + 6,
          padding: d.rowPad,
          background: selected ? "rgba(255,75,75,0.06)" : (hover ? "var(--surface)" : "transparent"),
          border: `1px solid ${selected ? "rgba(255,75,75,0.35)" : "var(--border)"}`,
          borderRadius: 8, cursor: "pointer", position: "relative",
          transition: "background 120ms, border-color 120ms",
          opacity: dragHandle["data-dragging"] === "true" ? 0.4 : 1,
        }}>
        {/* drag handle + section color bar */}
        <div {...dragHandle}
              onClick={(e) => e.stopPropagation()}
              style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0,
                        cursor: "grab" }}
              title="Drag to reorder">
          <Icon name="grip-vertical" size={14} style={{ color: "var(--text-dim)" }} />
          <span style={{ width: 3, alignSelf: "stretch", borderRadius: 2,
                         background: sectionColor, opacity: 0.55, minHeight: d.thumb * 0.55 }} />
        </div>

        <ClipThumb seg={seg} w={d.thumb} />

        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 4 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: d.font, fontWeight: 600, color: "var(--text)",
                           overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {seg.title}
            </span>
            {seg.temp !== 0 && (
              <Pill tone={seg.temp > 0 ? "warn" : "info"} style={{ padding: "1px 6px", fontSize: 10 }}>
                {seg.temp > 0 ? "+" : ""}{seg.temp}K
              </Pill>
            )}
          </div>
          <div className="mono" style={{
            fontSize: d.sub, color: "var(--text-dim)", display: "flex", gap: 10,
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          }}>
            <span>{seg.file}</span>
          </div>
        </div>

        <AudioModeBadge mode={seg.audio} />

        <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
          <DevicePills channels={seg.channels} />
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 2 }}>
          {inspectorMode === "inline" && (
            <Button kind="ghost" size="icon" onClick={(e) => { e.stopPropagation(); onToggleExpand(); }}
                    title={expanded ? "Collapse" : "Edit details"}>
              <Icon name={expanded ? "chevron-up" : "chevron-down"} size={14} />
            </Button>
          )}
          <Button kind="ghost" size="icon" title="Edit clip (trim · audio · remove)"
                  onClick={(e) => { e.stopPropagation(); onEditClip?.(seg); }}><Icon name="pencil" size={13} /></Button>
        </div>
      </div>
      <DropLine on={drop.hoverPosition === "after"} />
    </>
  );
}

// ── Clip editor dialog ────────────────────────────────────────────
// Opened from a clip's pencil. Sets the trim window (in/out), the audio
// treatment, and hosts Remove (the per-clip trashcan moved in here).
function _fmtSecs(ms) {
  const t = Math.max(0, Math.round(ms / 1000));
  const m = Math.floor(t / 60), s = t % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}
function ClipEditor({ seg, onSave, onRemove, onClose }) {
  const durMs = seg.durMs || 0;
  const [audio, setAudio] = bsState(seg.audio || "keep");
  const [startS, setStartS] = bsState(String((seg.trimStartMs ?? 0) / 1000));
  const [endS, setEndS] = bsState(String((seg.trimEndMs ?? durMs) / 1000));

  bsUseEffect(() => {
    function k(e) { if (e.key === "Escape") onClose(); }
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);

  function commit() {
    const sMs = Math.max(0, Math.round((parseFloat(startS) || 0) * 1000));
    const eMs = Math.round((parseFloat(endS) || 0) * 1000);
    onSave(seg.id, {
      audio,
      trimStartMs: sMs > 0 ? sMs : 0,
      // end at/after full length (or unset) → play to the source end.
      trimEndMs: (durMs && (eMs <= 0 || eMs >= durMs)) ? null : (eMs > 0 ? eMs : null),
    });
    onClose();
  }

  const AUDIO_OPTS = [
    { v: "keep", label: "Keep", icon: "volume-2" },
    { v: "replace", label: "Replace", icon: "music" },
    { v: "silence", label: "Silence", icon: "volume-x" },
  ];

  return (
    <div onClick={onClose} style={{
      position: "fixed", inset: 0, zIndex: 50,
      background: "rgba(0,0,0,0.6)", display: "grid", placeItems: "center",
    }}>
      <div onClick={(e) => e.stopPropagation()} style={{
        width: 460, maxHeight: "94vh", overflowY: "auto",
        background: "var(--surface)", border: "1px solid var(--border)",
        borderRadius: 12, boxShadow: "var(--elev-3)",
      }}>
        <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--border)",
                       display: "flex", alignItems: "center", gap: 10 }}>
          <Icon name="pencil" size={15} style={{ color: "var(--accent-warm)" }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 14, fontWeight: 600 }}>Edit clip</div>
            <div className="mono" style={{ fontSize: 11, color: "var(--text-dim)",
                                            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {seg.title || seg.file}
            </div>
          </div>
          <Button kind="ghost" size="icon" onClick={onClose}><Icon name="x" size={14} /></Button>
        </div>

        <div style={{ padding: 18, display: "flex", flexDirection: "column", gap: 16 }}>
          {/* Trim */}
          <div>
            <FASectionLabel>Trim window</FASectionLabel>
            <div style={{ fontSize: 11.5, color: "var(--text-muted)", margin: "2px 0 10px" }}>
              In / out points in seconds. {durMs ? <>Source is <span className="mono" style={{ color: "var(--text)" }}>{_fmtSecs(durMs)}</span>.</> : "Duration not probed yet."}
            </div>
            <div style={{ display: "flex", gap: 10 }}>
              <Field label="Start (s)" style={{ flex: 1 }}>
                <TextInput value={startS} onChange={setStartS} mono />
              </Field>
              <Field label="End (s)" style={{ flex: 1 }}>
                <TextInput value={endS} onChange={setEndS} mono />
              </Field>
            </div>
            <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 8 }}>
              To find a cut point by eye, select the clip and use the
              Inspector's Source tab — it previews the video against these
              same in / out points.
            </div>
          </div>

          {/* Audio */}
          <div>
            <FASectionLabel>Audio</FASectionLabel>
            <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
              {AUDIO_OPTS.map(o => (
                <button key={o.v} onClick={() => setAudio(o.v)} style={{
                  flex: 1, display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 6,
                  padding: "8px 10px", borderRadius: 6, cursor: "pointer", fontFamily: "inherit",
                  fontSize: 12, fontWeight: 600,
                  background: audio === o.v ? "var(--accent-warm)" : "var(--surface-2)",
                  color: audio === o.v ? "#1a1a1a" : "var(--text-muted)",
                  border: `1px solid ${audio === o.v ? "var(--accent-warm)" : "var(--border)"}`,
                }}>
                  <Icon name={o.icon} size={13} /> {o.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8,
                       padding: "14px 18px", borderTop: "1px solid var(--border)" }}>
          <Button kind="ghost" size="sm" icon="trash-2"
                  onClick={() => { onRemove(seg.id); onClose(); }}
                  style={{ color: "var(--danger)" }}>Remove clip</Button>
          <div style={{ flex: 1 }} />
          <Button kind="ghost" size="sm" onClick={onClose}>Cancel</Button>
          <Button kind="primary" size="sm" icon="check" onClick={commit}>Save</Button>
        </div>
      </div>
    </div>
  );
}

// ── Inline-expand panel (when inspectorMode = "inline") ────────────
function InlineEditor({ seg, onClose }) {
  return (
    <div style={{
      margin: "4px 0 10px 32px",
      padding: 16,
      background: "var(--surface-2)",
      border: "1px solid var(--border)",
      borderRadius: 8,
      display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16,
    }}>
      <div>
        <FASectionLabel>Source</FASectionLabel>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <Field label="File"><TextInput value={seg.file} mono /></Field>
          <div style={{ display: "flex", gap: 8 }}>
            <Field label="Trim in"><TextInput value="00:00.000" mono style={{ width: 110 }} /></Field>
            <Field label="Trim out"><TextInput value={fmtTotal(seg.durMs)} mono style={{ width: 110 }} /></Field>
          </div>
        </div>
      </div>
      <div>
        <FASectionLabel>Color temperature</FASectionLabel>
        <Slider value={seg.temp + 6500} min={4000} max={10000} step={100}
                onChange={() => {}} label={`${seg.temp >= 0 ? "+" : ""}${seg.temp}K offset`}
                valueLabel={`${6500 + seg.temp}K`} />
        <div style={{ marginTop: 12 }}>
          <Button kind="secondary" size="sm" icon="camera">Preview frame</Button>
        </div>
      </div>
      <div style={{ gridColumn: "1 / -1", display: "flex", justifyContent: "flex-end" }}>
        <Button kind="ghost" size="sm" onClick={onClose}>Done</Button>
      </div>
    </div>
  );
}

// ── Joiner element — three styles ─────────────────────────────────
function JoinerEl({ joiner, userJoiners, style: jStyle, onClick }) {
  const isCut = joiner.kind === "none";
  const label = FA_DATA.joinerShortLabel(joiner, userJoiners);
  const kind = FA_DATA.joinerKind(joiner);

  // Wrap click to send back the bounding rect so the editor anchors.
  function handleClick(e) {
    onClick(e.currentTarget.getBoundingClientRect());
  }

  if (jStyle === "divider") {
    return (
      <button onClick={handleClick} style={{
        display: "flex", alignItems: "center", gap: 12, width: "100%",
        padding: "8px 14px", background: "transparent", border: "none",
        cursor: "pointer", color: "var(--text-dim)", fontFamily: "inherit",
      }}>
        <span style={{ flex: 1, height: 1, background: "var(--border)" }} />
        <span className="mono" style={{ fontSize: 10.5, letterSpacing: "0.08em", textTransform: "uppercase",
                                        color: isCut ? "var(--text-dim)" : "var(--accent-warm)" }}>
          ↳ {label}
        </span>
        <span style={{ flex: 1, height: 1, background: "var(--border)" }} />
      </button>
    );
  }
  if (jStyle === "lane") {
    return (
      <div style={{ display: "flex", padding: "4px 0", paddingLeft: 22 }}>
        <button onClick={handleClick} style={{
          display: "inline-flex", alignItems: "center", gap: 6,
          padding: "4px 10px", border: `1px solid var(--border)`,
          background: "var(--surface-2)", borderRadius: 5,
          color: isCut ? "var(--text-muted)" : "var(--accent-warm)",
          fontSize: 11, fontWeight: 600, cursor: "pointer",
        }}>
          <Icon name={kind.icon} size={12} />
          <span className="mono">{label}</span>
        </button>
      </div>
    );
  }
  // inline-pill (default — novel treatment, straddles row gap)
  return (
    <div style={{ position: "relative", height: 14, margin: "-7px 0", zIndex: 2,
                  display: "flex", justifyContent: "center", pointerEvents: "none" }}>
      <button onClick={handleClick} style={{
        pointerEvents: "auto",
        display: "inline-flex", alignItems: "center", gap: 6,
        padding: "3px 10px", borderRadius: 999, border: "1px solid var(--border)",
        background: isCut ? "var(--surface-2)" : "rgba(255,140,66,0.12)",
        color: isCut ? "var(--text-muted)" : "var(--accent-warm)",
        fontFamily: "var(--font-mono)", fontSize: 10.5, fontWeight: 600,
        cursor: "pointer", letterSpacing: "0.04em",
        boxShadow: isCut ? "none" : "0 0 0 1px rgba(255,140,66,0.25)",
      }}>
        <Icon name={kind.icon} size={11} />
        {label}
        <Icon name="chevron-down" size={11} style={{ opacity: 0.7 }} />
      </button>
    </div>
  );
}

// ── Section header (sections layout) ──────────────────────────────
function SectionHeader({ section, idx, total, density, chapterStartMs, onAddTitle, onAddClips, onAddClip, onRename, onRemove }) {
  const dragHandle = useDraggable({ kind: "section", id: section.id });
  const drop = useDroppable({ accept: "section", id: section.id });
  const [editing, setEditing] = bsState(false);
  const [draftTitle, setDraftTitle] = bsState(section.title);
  bsUseEffect(() => { setDraftTitle(section.title); }, [section.title]);
  const inputRef = bsRef();
  bsUseEffect(() => { if (editing) inputRef.current?.select(); }, [editing]);

  function commit() {
    const next = draftTitle.trim() || section.title;
    if (next !== section.title) onRename?.(section.id, next);
    setEditing(false);
  }

  return (
    <>
      <DropLine on={drop.hoverPosition === "before"} />
      <div ref={drop.ref} {...drop.handlers}
            style={{
              display: "flex", alignItems: "center", gap: 10,
              padding: "10px 4px 8px",
              opacity: dragHandle["data-dragging"] === "true" ? 0.4 : 1,
            }}>
        <span {...dragHandle}
              style={{ display: "inline-flex", padding: 2,
                        color: "var(--text-dim)", cursor: "grab" }}
              title="Drag section to reorder">
          <Icon name="grip-vertical" size={14} />
        </span>
        <span style={{ width: 10, height: 10, borderRadius: 2, background: section.color }} />
        <span className="mono" style={{ fontSize: 10.5, color: "var(--text-dim)", fontWeight: 700,
                                        letterSpacing: "0.1em", textTransform: "uppercase" }}>
          {String(idx + 1).padStart(2, "0")} / {String(total).padStart(2, "0")}
        </span>

        {editing ? (
          <input
            ref={inputRef} value={draftTitle}
            onChange={(e) => setDraftTitle(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => {
              if (e.key === "Enter") commit();
              if (e.key === "Escape") { setDraftTitle(section.title); setEditing(false); }
            }}
            style={{
              fontFamily: "inherit", fontSize: 14, fontWeight: 600,
              color: "var(--text)", background: "var(--surface-2)",
              border: "1px solid var(--accent)", borderRadius: 4,
              padding: "1px 6px", outline: "none", minWidth: 120,
            }} />
        ) : (
          <h3 onClick={() => setEditing(true)}
              title="Click to rename — also becomes the chapter marker name"
              style={{
                fontSize: 14, fontWeight: 600, margin: 0, color: "var(--text)",
                cursor: "text", padding: "1px 6px", borderRadius: 4,
                border: "1px solid transparent",
              }}>
            {section.title}
          </h3>
        )}

        {/* Chapter affordance — this section becomes chapter N in the output */}
        <span title={`Becomes chapter marker ${String(idx + 1).padStart(2, "0")} in the output MP4 + funscript`}
               style={{
                 display: "inline-flex", alignItems: "center", gap: 4,
                 padding: "1px 7px", borderRadius: 4,
                 background: "rgba(255,140,66,0.10)",
                 border: "1px solid rgba(255,140,66,0.28)",
                 color: "var(--accent-warm)",
                 fontFamily: "var(--font-mono)", fontSize: 10.5, fontWeight: 600,
                 letterSpacing: "0.04em",
               }}>
          <Icon name="bookmark" size={11} />
          ch.{String(idx + 1).padStart(2, "0")}
          {chapterStartMs != null && (
            <span style={{ opacity: 0.7, marginLeft: 2 }}>
              @ {fmtTotal(chapterStartMs)}
            </span>
          )}
        </span>

        <Pill style={{ fontSize: 10 }}>{section.segments.length} clip{section.segments.length === 1 ? "" : "s"}</Pill>
        <div style={{ flex: 1 }} />
        <Button kind="ghost" size="sm" icon="image-plus" onClick={() => onAddTitle?.(section.id)}>Title card</Button>
        <Button kind="ghost" size="sm" icon="plus" onClick={() => onAddClip?.(section.id)}>Add clip</Button>
        <Button kind="ghost" size="icon" title="Rename / configure"
                onClick={() => setEditing(true)}><Icon name="pencil" size={14} /></Button>
        {total > 1 && (
          <Button kind="ghost" size="icon" title="Remove section"
                  onClick={() => {
                    if (section.segments.length &&
                        !window.confirm(`Remove section "${section.title || 'Untitled'}" and its ${section.segments.length} clip${section.segments.length === 1 ? '' : 's'}?`))
                      return;
                    onRemove?.(section.id);
                  }}><Icon name="trash-2" size={14} /></Button>
        )}
      </div>
      <DropLine on={drop.hoverPosition === "after"} />
    </>
  );
}

// ── Layout: sections ──────────────────────────────────────────────
function LayoutSections({ project, density, joinerStyle, selectedIds, onSelect, expandedId, onToggleExpand, inspectorMode, sectionGrouping, onEditJoiner, onOpenTitleEditor, onRenameSection, onAddClips, onAddClip, onAddSection, onRemoveSection, onEditClip, onAddTransition }) {
  // If section grouping is OFF, fall back to flat layout
  if (!sectionGrouping) return <LayoutFlat
    project={project} density={density} joinerStyle={joinerStyle}
    selectedIds={selectedIds} onSelect={onSelect}
    expandedId={expandedId} onToggleExpand={onToggleExpand} inspectorMode={inspectorMode}
    onEditJoiner={onEditJoiner} onOpenTitleEditor={onOpenTitleEditor} onAddClips={onAddClips} onAddClip={onAddClip} onEditClip={onEditClip} />;

  // Precompute each section's chapter start time (sum of all preceding
  // section durations + their leading joiner totals).
  let cursor = 0;
  const sectionStarts = {};
  for (let i = 0; i < project.sections.length; i++) {
    sectionStarts[project.sections[i].id] = cursor;
    cursor += project.sections[i].segments.reduce((a, s) => a + s.durMs, 0);
    if (i < project.sections.length - 1) {
      const nextJoiner = project.sections[i + 1].joiner;
      if (nextJoiner && nextJoiner.kind !== "none") {
        cursor += FA_DATA.joinerTotalMs(nextJoiner);
      }
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {project.sections.map((sec, sIdx) => (
        <React.Fragment key={sec.id}>
          {sIdx > 0 && <JoinerEl joiner={sec.joiner} userJoiners={project.userJoiners}
                                   style={joinerStyle}
                                   onClick={(rect) => onEditJoiner(sec.id, rect)} />}
          <div style={{ padding: "4px 0 10px" }}>
            <SectionHeader section={sec} idx={sIdx} total={project.sections.length}
                            density={density}
                            chapterStartMs={sectionStarts[sec.id]}
                            onAddTitle={(sectionId) => onOpenTitleEditor(sectionId)}
                            onAddClips={onAddClips}
                            onAddClip={onAddClip}
                            onRename={onRenameSection}
                            onRemove={onRemoveSection} />
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {sec.segments.length > 0 && (
                <InsertContentButton
                  onAddClip={() => onAddClip?.(sec.id, 0)}
                  onAddTitle={() => onOpenTitleEditor(sec.id)} />
              )}
              {sec.segments.map((seg, i) => (
                <React.Fragment key={seg.id}>
                  <ClipRow seg={seg} sectionColor={sec.color} sectionId={sec.id} density={density}
                           selected={selectedIds.includes(seg.id)}
                           onSelect={(e) => onSelect(seg.id, e)}
                           expanded={expandedId === seg.id} onToggleExpand={() => onToggleExpand(seg.id)}
                           inspectorMode={inspectorMode} onEditClip={onEditClip} />
                  {expandedId === seg.id && inspectorMode === "inline" &&
                    <InlineEditor seg={seg} onClose={() => onToggleExpand(seg.id)} />}
                  {i < sec.segments.length - 1 && (
                    <AddTransitionButton
                      onPick={(rect) => onAddTransition?.(sec.id, seg.id, rect)} />
                  )}
                </React.Fragment>
              ))}
            </div>
          </div>
        </React.Fragment>
      ))}
      <AddSectionButton onAddSection={onAddSection} />
    </div>
  );
}

// A "+" that sits between two clips in a section. Clicking it inserts a
// transition there — under the hood it splits the section so the joiner has a
// boundary to live on (every joiner is also a chapter marker).
function AddTransitionButton({ onPick }) {
  const [hover, setHover] = bsState(false);
  return (
    <div onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
         style={{ display: "flex", alignItems: "center", justifyContent: "center",
                  height: 14, position: "relative" }}>
      <div style={{ position: "absolute", left: 0, right: 0, height: 1,
                     background: hover ? "var(--accent-warm)" : "transparent",
                     opacity: 0.4, transition: "background 0.12s" }} />
      <button title="Add a transition here"
        onClick={(e) => { e.stopPropagation(); onPick?.(e.currentTarget.getBoundingClientRect()); }}
        style={{ position: "relative", display: "inline-flex", alignItems: "center",
                 justifyContent: "center", width: 20, height: 20, borderRadius: 10,
                 cursor: "pointer", fontFamily: "inherit",
                 background: hover ? "var(--accent-warm)" : "var(--surface-2)",
                 color: hover ? "#1a1a1a" : "var(--text-dim)",
                 border: `1px solid ${hover ? "var(--accent-warm)" : "var(--border)"}`,
                 opacity: hover ? 1 : 0.6, transition: "all 0.12s" }}>
        <Icon name="plus" size={12} />
      </button>
    </div>
  );
}

// A "+" above the FIRST clip of a section. The one between clips adds a
// transition; there is no clip before this one to transition from, so this
// one inserts content instead — the lead-in you want at the top.
function InsertContentButton({ onAddClip, onAddTitle }) {
  const [hover, setHover] = bsState(false);
  const [open, setOpen] = bsState(false);

  // Click-away: the menu is small and modeless, so anything outside closes it.
  React.useEffect(() => {
    if (!open) return undefined;
    const close = () => setOpen(false);
    window.addEventListener("mousedown", close);
    window.addEventListener("keydown", close);
    return () => {
      window.removeEventListener("mousedown", close);
      window.removeEventListener("keydown", close);
    };
  }, [open]);

  const item = {
    display: "flex", alignItems: "center", gap: 8, width: "100%",
    padding: "7px 12px", background: "transparent", border: "none",
    color: "var(--text)", fontSize: 12.5, fontFamily: "inherit",
    cursor: "pointer", textAlign: "left", whiteSpace: "nowrap",
  };

  return (
    <div onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
         style={{ display: "flex", alignItems: "center", justifyContent: "center",
                  height: 14, position: "relative" }}>
      <div style={{ position: "absolute", left: 0, right: 0, height: 1,
                     background: hover || open ? "var(--accent-warm)" : "transparent",
                     opacity: 0.4, transition: "background 0.12s" }} />
      <button title="Insert a clip or title card above"
        onMouseDown={(e) => e.stopPropagation()}
        onClick={(e) => { e.stopPropagation(); setOpen(o => !o); }}
        style={{ position: "relative", display: "inline-flex", alignItems: "center",
                 justifyContent: "center", width: 20, height: 20, borderRadius: 10,
                 cursor: "pointer", fontFamily: "inherit",
                 background: hover || open ? "var(--accent-warm)" : "var(--surface-2)",
                 color: hover || open ? "#1a1a1a" : "var(--text-dim)",
                 border: `1px solid ${hover || open ? "var(--accent-warm)" : "var(--border)"}`,
                 opacity: hover || open ? 1 : 0.6, transition: "all 0.12s" }}>
        <Icon name="plus" size={12} />
      </button>
      {open && (
        <div onMouseDown={(e) => e.stopPropagation()}
             style={{ position: "absolute", top: 24, left: "50%", transform: "translateX(-50%)",
                      zIndex: 40, minWidth: 168, padding: "4px 0",
                      background: "var(--surface)", border: "1px solid var(--border)",
                      borderRadius: 8, boxShadow: "0 10px 28px rgba(0,0,0,0.45)" }}>
          <button style={item} onClick={() => { setOpen(false); onAddClip?.(); }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = "var(--surface-2)")}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
            <Icon name="plus" size={13} /> Add clip…
          </button>
          <button style={item} onClick={() => { setOpen(false); onAddTitle?.(); }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = "var(--surface-2)")}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
            <Icon name="image-plus" size={13} /> Title card…
          </button>
        </div>
      )}
    </div>
  );
}

function AddSectionButton({ onAddSection }) {
  return (
    <button onClick={() => onAddSection?.()} style={{
      display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
      padding: "14px", marginTop: 8,
      background: "transparent", border: "1px dashed var(--border)",
      borderRadius: 8, color: "var(--text-muted)",
      cursor: "pointer", fontFamily: "inherit", fontSize: 12.5, fontWeight: 600,
    }}>
      <Icon name="plus" size={14} /> Add section
    </button>
  );
}

// ── Layout: flat ──────────────────────────────────────────────────
function LayoutFlat({ project, density, joinerStyle, selectedIds, onSelect, expandedId, onToggleExpand, inspectorMode, onEditJoiner, onAddClips, onAddClip, onEditClip }) {
  const flat = [];
  for (const sec of project.sections) {
    for (let i = 0; i < sec.segments.length; i++) {
      flat.push({ seg: sec.segments[i], sec, firstInSection: i === 0 });
    }
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {flat.map(({ seg, sec, firstInSection }, idx) => {
        const prev = idx > 0 ? flat[idx - 1] : null;
        let joiner = null, joinerSecId = null;
        if (prev) {
          joiner = firstInSection ? sec.joiner : { kind: "none" };
          joinerSecId = firstInSection ? sec.id : null;
        }
        return (
          <React.Fragment key={seg.id}>
            {joiner && <JoinerEl joiner={joiner} userJoiners={project.userJoiners}
                                   style={joinerStyle}
                                   onClick={(rect) => joinerSecId && onEditJoiner(joinerSecId, rect)} />}
            <ClipRow seg={seg} sectionColor={sec.color} sectionId={sec.id} density={density}
                     selected={selectedIds.includes(seg.id)}
                     onSelect={(e) => onSelect(seg.id, e)}
                     expanded={expandedId === seg.id} onToggleExpand={() => onToggleExpand(seg.id)}
                     inspectorMode={inspectorMode} onEditClip={onEditClip} />
            {expandedId === seg.id && inspectorMode === "inline" &&
              <InlineEditor seg={seg} onClose={() => onToggleExpand(seg.id)} />}
          </React.Fragment>
        );
      })}
      <button onClick={() => onAddClip?.(null)} style={{
        display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
        padding: "14px", marginTop: 8,
        background: "transparent", border: "1px dashed var(--border)",
        borderRadius: 8, color: "var(--text-muted)",
        cursor: "pointer", fontFamily: "inherit", fontSize: 12.5, fontWeight: 600,
      }}>
        <Icon name="plus" size={14} /> Add clip
      </button>
    </div>
  );
}

// ── Layout: timeline (horizontal filmstrip) ───────────────────────
function LayoutTimeline({ project, density, joinerStyle, selectedIds, onSelect, onEditJoiner }) {
  // Each section becomes a band of card-thumbnails. Joiners are gaps with labels.
  const totalMs = project.sections.flatMap(s => s.segments).reduce((a, s) => a + s.durMs, 0);
  const minPxPerSec = density === "compact" ? 1.2 : density === "comfortable" ? 1.8 : 2.4;
  const cardH = density === "compact" ? 92 : density === "comfortable" ? 116 : 144;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {project.sections.map((sec, sIdx) => (
        <div key={sec.id}>
          {/* In timeline view, surface the section's leading joiner as
              an editable inline pill (same as other layouts). */}
          {sIdx > 0 && (
            <JoinerEl joiner={sec.joiner} userJoiners={project.userJoiners}
                       style={joinerStyle}
                       onClick={(rect) => onEditJoiner(sec.id, rect)} />
          )}
          <SectionHeader section={sec} idx={sIdx} total={project.sections.length} density={density} />
          <div style={{
            display: "flex", gap: 8, overflowX: "auto", paddingBottom: 8,
            scrollSnapType: "x mandatory",
          }}>
            {sec.segments.map((seg, i) => {
              const w = Math.max(140, Math.round(seg.durMs / 1000 * minPxPerSec * 6));
              const selected = selectedIds.includes(seg.id);
              return (
                <React.Fragment key={seg.id}>
                  {i > 0 && (
                    <div style={{ width: 2, alignSelf: "stretch",
                                  background: "var(--border)", flexShrink: 0,
                                  marginTop: 18, marginBottom: 18 }} title="cut" />
                  )}
                  <div onClick={(e) => onSelect(seg.id, e)} style={{
                    width: w, flexShrink: 0, scrollSnapAlign: "start",
                    background: "var(--surface)", border: `1px solid ${selected ? "rgba(255,75,75,0.5)" : "var(--border)"}`,
                    borderRadius: 8, padding: 8,
                    boxShadow: selected ? "0 0 0 1px rgba(255,75,75,0.3)" : "none",
                    cursor: "pointer",
                  }}>
                    <div style={{ position: "relative", width: "100%", height: cardH,
                                  borderRadius: 5, overflow: "hidden",
                                  background: "var(--surface-2)" }}>
                      <img src={seg.thumb} alt="" style={{ width: "100%", height: "100%",
                                                            display: "block", objectFit: "cover" }} />
                      <span style={{ position: "absolute", bottom: 4, right: 4,
                                      padding: "1px 5px", background: "rgba(0,0,0,0.7)",
                                      color: "#fff", fontFamily: "var(--font-mono)",
                                      fontSize: 10, fontWeight: 600, borderRadius: 2 }}>
                        {fmtClipDur(seg.durMs)}
                      </span>
                      {seg.kind === "still" && (
                        <span style={{ position: "absolute", top: 4, left: 4,
                                        padding: "1px 5px", background: "rgba(0,0,0,0.7)",
                                        color: "#fff", fontFamily: "var(--font-mono)",
                                        fontSize: 9, fontWeight: 700, letterSpacing: "0.06em",
                                        borderRadius: 2 }}>STILL</span>
                      )}
                    </div>
                    <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
                      <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text)",
                                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {seg.title}
                      </div>
                      <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                        <AudioModeBadge mode={seg.audio} />
                        {seg.channels.slice(0, 3).map(c => <ChannelChip key={c} id={c} />)}
                        {seg.channels.length > 3 &&
                          <span className="mono" style={{ fontSize: 10, color: "var(--text-dim)" }}>+{seg.channels.length - 3}</span>}
                      </div>
                    </div>
                  </div>
                </React.Fragment>
              );
            })}
            <button style={{
              width: 100, flexShrink: 0,
              display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
              border: "1px dashed var(--border)", background: "transparent",
              borderRadius: 8, color: "var(--text-muted)", cursor: "pointer",
              fontFamily: "inherit", fontSize: 12, fontWeight: 600,
            }}><Icon name="plus" size={14} /> Clip</button>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Cross-clip audio bed lane (novel) ─────────────────────────────
// One horizontal lane below the clip list (or above the preview band).
// Each bed is a colored segment that spans multiple clip durations.
function AudioBedLane({ project, density, onSelect, selectedBedId }) {
  const flat = project.sections.flatMap(s => s.segments);
  const totalMs = flat.reduce((a, s) => a + s.durMs, 0);

  // Compute % start/end of each bed.
  const beds = project.audioBeds.map(b => {
    let cursor = 0, startMs = 0, endMs = totalMs;
    for (const seg of flat) {
      if (seg.id === b.startSegmentId) startMs = cursor;
      cursor += seg.durMs;
      if (seg.id === b.endSegmentId)   endMs = cursor;
    }
    return { ...b, startPct: (startMs / totalMs) * 100, endPct: (endMs / totalMs) * 100 };
  });

  // Mini ticks: one per clip boundary, to show where cuts are.
  let cursor = 0;
  const ticks = flat.map(seg => {
    const t = (cursor / totalMs) * 100;
    cursor += seg.durMs;
    return { t, kind: seg.kind };
  });

  const laneH = density === "compact" ? 38 : density === "comfortable" ? 46 : 56;

  return (
    <div style={{
      background: "var(--surface)", border: "1px solid var(--border)",
      borderRadius: 10, padding: 12, marginTop: 16,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
        <Icon name="music-4" size={14} style={{ color: "var(--accent-warm)" }} />
        <span style={{ fontSize: 12.5, fontWeight: 600 }}>Audio bed</span>
        <Pill tone="accent" style={{ fontSize: 10 }}>new</Pill>
        <span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>
          A continuous audio layer that spans multiple clips. Ducks under or replaces per-clip audio across joiners.
        </span>
        <div style={{ flex: 1 }} />
        <span className="mono" style={{ fontSize: 11, color: "var(--text-dim)" }}>
          {project.audioBeds.length} bed{project.audioBeds.length === 1 ? "" : "s"}
        </span>
        <Button kind="secondary" size="sm" icon="plus">Add bed</Button>
      </div>

      <div style={{
        position: "relative", height: laneH,
        background: "var(--surface-2)", border: "1px solid var(--border)",
        borderRadius: 6, overflow: "hidden",
      }}>
        {/* clip-boundary tick marks */}
        {ticks.map((t, i) => (
          <span key={i} style={{
            position: "absolute", top: 0, bottom: 0, left: `${t.t}%`,
            width: 1, background: t.kind === "still" ? "rgba(255,140,66,0.35)" : "rgba(255,255,255,0.06)",
          }} />
        ))}

        {/* beds */}
        {beds.map((b, i) => (
          <button
            key={b.id}
            onClick={() => onSelect(b.id)}
            style={{
              position: "absolute", top: 5, bottom: 5,
              left: `${b.startPct}%`, width: `${b.endPct - b.startPct}%`,
              background: "linear-gradient(180deg, rgba(255,140,66,0.32), rgba(255,140,66,0.18))",
              border: `1px solid ${selectedBedId === b.id ? "var(--accent-warm)" : "rgba(255,140,66,0.5)"}`,
              borderRadius: 4, cursor: "pointer", overflow: "hidden",
              boxShadow: selectedBedId === b.id ? "0 0 0 1px rgba(255,140,66,0.35)" : "none",
              display: "flex", alignItems: "center", padding: "0 8px", gap: 6,
              color: "#fff", fontFamily: "inherit", textAlign: "left",
            }}
            title={b.title}
          >
            {/* fade-in/out triangles */}
            <span style={{
              position: "absolute", top: 0, bottom: 0, left: 0,
              width: `${Math.min(36, b.fadeInS * 4)}px`,
              background: "linear-gradient(90deg, rgba(0,0,0,0.55), transparent)",
              pointerEvents: "none",
            }} />
            <span style={{
              position: "absolute", top: 0, bottom: 0, right: 0,
              width: `${Math.min(36, b.fadeOutS * 4)}px`,
              background: "linear-gradient(270deg, rgba(0,0,0,0.55), transparent)",
              pointerEvents: "none",
            }} />

            {/* fake waveform */}
            <svg viewBox="0 0 200 30" preserveAspectRatio="none" style={{
              position: "absolute", inset: 0, width: "100%", height: "100%",
              opacity: 0.45, pointerEvents: "none",
            }}>
              {Array.from({ length: 60 }, (_, k) => {
                const x = (k / 59) * 200;
                const h = 5 + 11 * Math.abs(Math.sin(k * 0.6 + i)) + 4 * Math.abs(Math.cos(k * 1.3 + i * 2));
                return <line key={k} x1={x} x2={x} y1={15 - h / 2} y2={15 + h / 2}
                              stroke="#fff" strokeWidth="1.2" />;
              })}
            </svg>

            <Icon name="music" size={12} style={{ position: "relative", flexShrink: 0 }} />
            <span style={{
              position: "relative", fontSize: 11.5, fontWeight: 600,
              overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
            }}>{b.title}</span>
            <span className="mono" style={{ position: "relative", fontSize: 10,
                                              opacity: 0.85, marginLeft: "auto" }}>
              {b.level}dB · in {b.fadeInS}s · out {b.fadeOutS}s
              {b.duckUnderSegmentAudio ? " · duck" : " · solo"}
            </span>
          </button>
        ))}

        {project.audioBeds.length === 0 && (
          <span style={{
            position: "absolute", inset: 0, display: "grid", placeItems: "center",
            color: "var(--text-dim)", fontSize: 11.5,
          }}>Drop an audio file here to lay it across clips — or click <span style={{ color: "var(--text-muted)", margin: "0 4px" }}>Add bed</span></span>
        )}
      </div>
    </div>
  );
}

// ── Main BuildTab ─────────────────────────────────────────────────
function BuildTab({ project, density, buildLayout, joinerStyle, sectionGrouping,
                    inspectorMode, selectedIds, onSelect,
                    expandedId, onToggleExpand,
                    selectedBedId, onSelectBed,
                    onClearSelection,
                    onEditJoiner, onOpenTitleEditor, onRenameSection, onAddClips, onAddClip, onAddForgeScene, onAddSection, onRemoveSection, onEditClip, onAddTransition }) {

  const totalMs = project.sections.flatMap(s => s.segments).reduce((a, s) => a + s.durMs, 0);
  const segCount = project.sections.flatMap(s => s.segments).length;

  let main;
  if (buildLayout === "flat") {
    main = <LayoutFlat
      project={project} density={density} joinerStyle={joinerStyle}
      selectedIds={selectedIds} onSelect={onSelect}
      expandedId={expandedId} onToggleExpand={onToggleExpand}
      inspectorMode={inspectorMode} onEditJoiner={onEditJoiner}
      onOpenTitleEditor={onOpenTitleEditor} onAddClips={onAddClips} onAddClip={onAddClip} onEditClip={onEditClip} />;
  } else if (buildLayout === "timeline") {
    main = <LayoutTimeline
      project={project} density={density} joinerStyle={joinerStyle}
      selectedIds={selectedIds} onSelect={onSelect}
      onEditJoiner={onEditJoiner} />;
  } else {
    main = <LayoutSections
      project={project} density={density} joinerStyle={joinerStyle}
      selectedIds={selectedIds} onSelect={onSelect}
      expandedId={expandedId} onToggleExpand={onToggleExpand}
      inspectorMode={inspectorMode} sectionGrouping={sectionGrouping}
      onEditJoiner={onEditJoiner} onOpenTitleEditor={onOpenTitleEditor}
      onRenameSection={onRenameSection} onAddClips={onAddClips} onAddClip={onAddClip} onAddSection={onAddSection}
      onRemoveSection={onRemoveSection} onEditClip={onEditClip} onAddTransition={onAddTransition} />;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 0, paddingBottom: 4 }}>
      <FATabHeader
        eyebrow="Pipeline · 02 of 04"
        title="Build the sequence"
        subtitle="Add clips, group them into sections, and choose how each section transitions in. The audio-bed lane below lets a single sound piece span many clips — no per-clip audio cuts at joiners."
        right={
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Button kind="secondary" size="sm" icon="folder-plus"
                     onClick={() => onAddClips?.(null)}>Add folder…</Button>
            <Button kind="secondary" size="sm" icon="package"
                     onClick={() => onAddForgeScene?.(null)}>Add .forge scene…</Button>
            <Button kind="primary" size="sm" icon="type"
                     onClick={() => onOpenTitleEditor()}>New title card</Button>
          </div>
        } />

      {/* Stats strip */}
      <div style={{
        display: "flex", alignItems: "center", gap: 18,
        padding: "10px 14px", marginBottom: 14,
        background: "var(--surface-2)", border: "1px solid var(--border)",
        borderRadius: 8,
      }}>
        <StatItem label="Total duration" value={fmtTotal(totalMs)} mono />
        <Divider />
        <StatItem label="Sections" value={project.sections.length} />
        <Divider />
        <StatItem label="Segments" value={segCount} />
        <Divider />
        <StatItem label="Audio beds" value={project.audioBeds.length} />
        <Divider />
        <StatItem label="Resolution" value={project.output.resolution} mono />
        <div style={{ flex: 1 }} />
        <span className="mono" style={{ fontSize: 11, color: "var(--text-dim)" }}>
          layout: {buildLayout} · density: {density}
        </span>
      </div>

      {main}

      <AudioBedLane project={project}
                    onSelect={onSelectBed} selectedBedId={selectedBedId} />
    </div>
  );
}

function StatItem({ label, value, mono }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.2, whiteSpace: "nowrap" }}>
      <span style={{ fontSize: 10.5, fontWeight: 700, color: "var(--text-dim)",
                     textTransform: "uppercase", letterSpacing: "0.08em" }}>{label}</span>
      <span className={mono ? "mono" : ""} style={{ fontSize: 14, fontWeight: 600, color: "var(--text)" }}>
        {value}
      </span>
    </div>
  );
}
function Divider() {
  return <span style={{ width: 1, alignSelf: "stretch", background: "var(--border)" }} />;
}

Object.assign(window, { BuildTab });


export { AddSectionButton, AudioBedLane, AudioModeBadge, BuildTab, ChannelChip, ClipEditor, ClipRow, ClipThumb, DENSITY, DevicePills, Divider, InlineEditor, JoinerEl, LayoutFlat, LayoutSections, LayoutTimeline, SectionHeader, StatItem };
