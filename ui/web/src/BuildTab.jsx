/* @esm-converted */
import React from 'react';
import { FASectionLabel, FATabHeader, fmtClipDur, fmtTotal } from './AppShell';
import { FA_DATA } from './data';
import { DropLine, useDraggable, useDroppable } from './dragdrop';
import { Button, Field, Icon, Pill, TextInput } from './primitives';
import { toMediaUrl } from './lib/mediaUrl';
import { channelGapsFor, channelName, effectiveDurMs,
         projectDurationMs } from './lib/projectAdapter';

// ForgeAssembler — Build tab.
//
// A compilation is an ordered list of finished `.forge` SCENES with a
// joiner between each pair. One scene is one section is one clip is one
// row is one chapter — nothing in the app can put a second clip inside a
// section, so the canvas is a flat list rather than a tree.
//
// There used to be three interchangeable layouts, three joiner
// treatments, three density steps and two inspector modes, switchable
// only from a hidden design panel. They were prototype material: every
// combination had to keep working and none of them was a choice a user
// could make. One shape, chosen, is the whole of it now.

const { useState: bsState, useRef: bsRef, useEffect: bsUseEffect } = React;

// ── Row metrics ───────────────────────────────────────────────────
// One set, not three switchable ones.
const ROW = { thumb: 76, pad: "12px 14px", gap: 10, font: 13, sub: 11.5 };

// Which raw channel names belong to which device group. These lived next
// to the (now deleted) ChannelChip and went out with it, which left
// bucketChannels referencing two names that no longer existed — a crash
// on the first scene row, because nothing evaluates it until one renders.
const _MULTI_AXIS = new Set(["surge", "sway", "twist", "roll", "pitch"]);
const _DEVICE_META = {
  stroke:    { label: "Stroke",     color: "#ff7b7b" },
  multiaxis: { label: "Multi-axis", color: "#4dabf7" },
  estim:     { label: "E-Stim",     color: "#3ed598" },
};

function bucketChannels(channels) {
  const g = { stroke: [], multiaxis: [], estim: [] };
  for (const c of channels || []) {
    // Keys are station-qualified (`focstim:alpha`), so bucket on the channel
    // inside the key — otherwise every station's channels read as e-stim.
    const name = channelName(c);
    if (name === "main") g.stroke.push(c);
    else if (_MULTI_AXIS.has(name)) g.multiaxis.push(c);
    else g.estim.push(c);
  }
  return g;
}
// A `.forge` that shipped no analysis sidecars. Not an output problem —
// the forge is identical either way — but the preview has to decode the
// video to draw a waveform, so it's worth knowing before you wonder why
// scrubbing is slow. Quieter than the gap flag on purpose.
function LeanPill() {
  return (
    <span title="This bundle carries no analysis — waveform and beats are derived from the video, which is slower. Re-export from FunscriptForge to include them."
           style={{
      display: "inline-flex", alignItems: "center",
      padding: "1px 6px", borderRadius: 4, fontSize: 10.5,
      fontFamily: "var(--font-mono)", color: "var(--text-dim)",
      border: "1px solid var(--border)",
    }}>
      <Icon name="file-question" size={10} />
    </span>
  );
}

// A clip that's missing what its neighbours have. Hover names them.
function GapPill({ gaps }) {
  if (!gaps.length) return null;
  return (
    <span title={`Blank for this clip: ${gaps.join(", ")}`} style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      padding: "1px 8px", borderRadius: 4, fontSize: 10.5, fontWeight: 600,
      fontFamily: "var(--font-mono)", letterSpacing: "0.02em",
      background: "#ffb54722", color: "var(--warn)",
      border: "1px solid #ffb54744",
    }}>
      <Icon name="triangle-alert" size={10} />
      {gaps.length} gap{gaps.length === 1 ? "" : "s"}
    </span>
  );
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

// ── Clip editor dialog ────────────────────────────────────────────
// Opened from a scene row's pencil. Sets the trim window (in/out) and the
// audio treatment, and hosts Remove.
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

// ── Scene row ─────────────────────────────────────────────────────
// One .forge scene = one section = one clip = one row = one chapter.
// This row merges what used to be a section header and a clip row: with
// nothing able to put a second clip in a section, drawing both was two
// rows of chrome for the one thing the user thinks of as one scene.
//
// The name is editable in place because it is the CHAPTER name in the
// output, not decoration.
function SceneRow({ section, seg, idx, chapterStartMs, selected,
                    onSelect, onRename, onRemove, onEditClip, gaps = [] }) {
  const drag = useDraggable({ kind: "section", id: section.id });
  const drop = useDroppable({ accept: "section", id: section.id });
  const [hover, setHover] = bsState(false);
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

  const sourceMs = seg.sourceDurMs ?? seg.durMs ?? 0;
  const trimmed = (seg.trimStartMs ?? 0) > 0
    || (seg.trimEndMs != null && sourceMs && seg.trimEndMs < sourceMs);

  return (
    <>
      <DropLine on={drop.hoverPosition === "before"} />
      <div
        ref={drop.ref}
        {...drop.handlers}
        onClick={() => onSelect(seg.id)}
        onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
        style={{
          display: "flex", alignItems: "center", gap: ROW.gap + 6,
          padding: ROW.pad,
          background: selected ? "rgba(255,75,75,0.06)" : (hover ? "var(--surface)" : "transparent"),
          border: `1px solid ${selected ? "rgba(255,75,75,0.35)" : "var(--border)"}`,
          borderRadius: 8, cursor: "pointer", position: "relative",
          transition: "background 120ms, border-color 120ms",
          opacity: drag["data-dragging"] === "true" ? 0.4 : 1,
        }}>
        {/* drag handle + scene colour bar */}
        <div {...drag}
              onClick={(e) => e.stopPropagation()}
              style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0, cursor: "grab" }}
              title="Drag to reorder the scenes">
          <Icon name="grip-vertical" size={14} style={{ color: "var(--text-dim)" }} />
          <span style={{ width: 3, alignSelf: "stretch", borderRadius: 2,
                         background: section.color, opacity: 0.55, minHeight: ROW.thumb * 0.55 }} />
        </div>

        <span className="mono" style={{ fontSize: 10.5, color: "var(--text-dim)", fontWeight: 700,
                                        letterSpacing: "0.08em", flexShrink: 0 }}>
          {String(idx + 1).padStart(2, "0")}
        </span>

        <ClipThumb seg={seg} w={ROW.thumb} />

        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 4 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {editing ? (
              <input
                ref={inputRef} value={draftTitle}
                onClick={(e) => e.stopPropagation()}
                onChange={(e) => setDraftTitle(e.target.value)}
                onBlur={commit}
                onKeyDown={(e) => {
                  if (e.key === "Enter") commit();
                  if (e.key === "Escape") { setDraftTitle(section.title); setEditing(false); }
                }}
                style={{
                  fontFamily: "inherit", fontSize: ROW.font, fontWeight: 600,
                  color: "var(--text)", background: "var(--surface-2)",
                  border: "1px solid var(--accent)", borderRadius: 4,
                  padding: "1px 6px", outline: "none", minWidth: 160,
                }} />
            ) : (
              <span
                onClick={(e) => { e.stopPropagation(); setEditing(true); }}
                title="Click to rename — this is the chapter name in the output"
                style={{
                  fontSize: ROW.font, fontWeight: 600, color: "var(--text)",
                  cursor: "text", padding: "1px 6px", marginLeft: -6, borderRadius: 4,
                  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                }}>
                {section.title || seg.title}
              </span>
            )}
            {/* This scene becomes chapter N in the output. */}
            <span title={`Becomes chapter marker ${String(idx + 1).padStart(2, "0")} in the output MP4 + funscript`}
                   style={{
                     display: "inline-flex", alignItems: "center", gap: 4, flexShrink: 0,
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
                <span style={{ opacity: 0.7, marginLeft: 2 }}>@ {fmtTotal(chapterStartMs)}</span>
              )}
            </span>
            {seg.temp !== 0 && (
              <Pill tone={seg.temp > 0 ? "warn" : "info"} style={{ padding: "1px 6px", fontSize: 10 }}>
                {seg.temp > 0 ? "+" : ""}{seg.temp}K
              </Pill>
            )}
          </div>
          <div className="mono" style={{
            fontSize: ROW.sub, color: "var(--text-dim)", display: "flex", gap: 10,
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          }}>
            <span>{seg.file}</span>
          </div>
        </div>

        {/* Trim state, on the row — a scene contributing less than its
            source is worth seeing without opening anything. */}
        {trimmed && (
          <span title={`Trimmed: uses ${_fmtSecs(seg.trimStartMs ?? 0)} to ${_fmtSecs(seg.trimEndMs ?? sourceMs)} of ${_fmtSecs(sourceMs)}`}
                 style={{
            display: "inline-flex", alignItems: "center", gap: 4, flexShrink: 0,
            padding: "1px 8px", borderRadius: 4, fontSize: 10.5, fontWeight: 600,
            fontFamily: "var(--font-mono)",
            background: "rgba(77,171,247,0.13)", color: "#4dabf7",
            border: "1px solid rgba(77,171,247,0.30)",
          }}>
            <Icon name="scissors" size={10} /> trimmed
          </span>
        )}

        <AudioModeBadge mode={seg.audio} />

        <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
          <DevicePills channels={seg.channels} />
          <GapPill gaps={gaps} />
          {seg.bundleLean && <LeanPill />}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 2 }}>
          <Button kind="ghost" size="icon" title="Trim the start or end, set audio, remove"
                  onClick={(e) => { e.stopPropagation(); onEditClip?.(seg); }}><Icon name="pencil" size={13} /></Button>
          <Button kind="ghost" size="icon" title="Remove this scene"
                  onClick={(e) => {
                    e.stopPropagation();
                    if (!window.confirm(`Remove "${section.title || seg.title}" from the compilation?`)) return;
                    onRemove?.(section.id);
                  }}><Icon name="trash-2" size={13} /></Button>
        </div>
      </div>
      <DropLine on={drop.hoverPosition === "after"} />
    </>
  );
}

// ── Joiner row ────────────────────────────────────────────────────
// The transition INTO the scene below. A section's leading joiner is what
// the engine renders at that boundary, so this sits above its own scene.
function JoinerRow({ joiner, onClick }) {
  const isCut = joiner.kind === "none";
  const label = FA_DATA.joinerShortLabel(joiner);

  return (
    <button onClick={(e) => onClick(e.currentTarget.getBoundingClientRect())} style={{
      display: "flex", alignItems: "center", gap: 12, width: "100%",
      padding: "8px 14px", background: "transparent", border: "none",
      cursor: "pointer", color: "var(--text-dim)", fontFamily: "inherit",
    }} title="Click to set the transition between these two scenes">
      <span style={{ flex: 1, height: 1, background: "var(--border)" }} />
      <span className="mono" style={{ fontSize: 10.5, letterSpacing: "0.08em", textTransform: "uppercase",
                                      color: isCut ? "var(--text-dim)" : "var(--accent-warm)" }}>
        &#8627; {label}
      </span>
      <span style={{ flex: 1, height: 1, background: "var(--border)" }} />
    </button>
  );
}

// ── The scene list ────────────────────────────────────────────────
function SceneList({ project, selectedIds, onSelect, onEditJoiner, onRenameSection,
                     onRemoveSection, onEditClip, onAddForgeScene }) {
  // Each scene's chapter start: the scenes before it, plus the joiners
  // between them (a joiner's bridge adds real time to the output).
  let cursor = 0;
  const starts = {};
  for (let i = 0; i < project.sections.length; i++) {
    starts[project.sections[i].id] = cursor;
    cursor += project.sections[i].segments.reduce((a, s) => a + effectiveDurMs(s), 0);
    const nextJoiner = project.sections[i + 1]?.joiner;
    if (nextJoiner) cursor += FA_DATA.joinerAddedMs(nextJoiner);
  }

  // A section with no clip is the empty boot state, not a scene.
  const scenes = project.sections
    .map(sec => ({ sec, seg: sec.segments[0] }))
    .filter(x => x.seg);

  if (!scenes.length) return <EmptyCanvas onAddForgeScene={onAddForgeScene} />;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {scenes.map(({ sec, seg }, i) => (
        <React.Fragment key={sec.id}>
          {i > 0 && <JoinerRow joiner={sec.joiner}
                                onClick={(rect) => onEditJoiner(sec.id, rect)} />}
          <SceneRow
            section={sec} seg={seg} idx={i}
            chapterStartMs={starts[sec.id]}
            selected={selectedIds.includes(seg.id)}
            onSelect={onSelect}
            onRename={onRenameSection}
            onRemove={onRemoveSection}
            onEditClip={onEditClip}
            gaps={channelGapsFor(seg, project)} />
        </React.Fragment>
      ))}
    </div>
  );
}

// What an empty compilation says. The old canvas showed an empty section
// header, which read as a broken row rather than as "nothing here yet".
function EmptyCanvas({ onAddForgeScene }) {
  return (
    <div style={{
      padding: "40px 24px", textAlign: "center",
      border: "1px dashed var(--border)", borderRadius: 10,
      background: "var(--surface-2)",
    }}>
      <Icon name="package-open" size={28} style={{ color: "var(--text-dim)" }} stroke={1.5} />
      <div style={{ fontSize: 14, fontWeight: 600, marginTop: 12 }}>No scenes yet</div>
      <div style={{ fontSize: 12.5, color: "var(--text-muted)", marginTop: 6, lineHeight: 1.5 }}>
        ForgeAssembler joins finished <span className="mono">.forge</span> scenes exported from
        FunscriptForge. Add two or more, then set the transition between them.
      </div>
      <div style={{ marginTop: 16 }}>
        <Button kind="primary" size="sm" icon="package"
                 onClick={() => onAddForgeScene?.()}>Add a .forge scene&#8230;</Button>
      </div>
    </div>
  );
}

// ── Build tab ─────────────────────────────────────────────────────
function BuildTab({ project, selectedIds, onSelect,
                    onEditJoiner, onRenameSection, onAddForgeFolder, onAddForgeScene,
                    onRemoveSection, onEditClip }) {

  const scenes = project.sections.filter(s => s.segments.length);
  const totalMs = projectDurationMs(project, FA_DATA.joinerAddedMs);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 0, paddingBottom: 4 }}>
      <FATabHeader
        eyebrow="Pipeline &#183; 02 of 04"
        title="Build the sequence"
        subtitle="Order the scenes, then click the line between any two to set how one becomes the next. Each scene is a chapter in the output."
        right={
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Button kind="secondary" size="sm" icon="folder-plus"
                     title="Pick a folder of finished .forge scenes — each becomes its own scene, and its own chapter"
                     onClick={() => onAddForgeFolder?.()}>Add folder&#8230;</Button>
            <Button kind="primary" size="sm" icon="package"
                     title="Add one finished .forge scene"
                     onClick={() => onAddForgeScene?.()}>Add .forge scene&#8230;</Button>
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
        <StatItem label="Scenes" value={scenes.length} />
        <Divider />
        <StatItem label="Chapters" value={scenes.length} />
        <Divider />
        <StatItem label="Resolution" value={project.output.resolution} mono />
      </div>

      <SceneList
        project={project}
        selectedIds={selectedIds}
        onSelect={onSelect}
        onEditJoiner={onEditJoiner}
        onRenameSection={onRenameSection}
        onRemoveSection={onRemoveSection}
        onEditClip={onEditClip}
        onAddForgeScene={onAddForgeScene} />
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


export { AudioModeBadge, BuildTab, ClipEditor, ClipThumb, DevicePills,
         Divider, EmptyCanvas, JoinerRow, ROW, SceneList, SceneRow, StatItem };
