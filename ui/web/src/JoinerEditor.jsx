/* @esm-converted */
import React from 'react';
import { JoinerEl } from './BuildTab';
import { VideoPoster } from './MediaViewer';
import { FA_DATA } from './data';
import { Button, Field, Icon, Pill, Slider, TextInput } from './primitives';

// JoinerEditor — popover anchored to a JoinerEl click.
// Lets the user pick a kind (built-in + user-authored presets), set
// the timing breakdown (fade out · hold · fade in for fade-style
// joiners; duration for others), and tune kind-specific params.

const { useEffect: jeUseEffect, useState: jeState, useRef: jeRef } = React;

// Apply a kind's defaults to produce a fresh joiner object.
function makeJoinerFromKind(kind) {
  const k = FA_DATA.JOINER_KINDS.find(x => x.kind === kind);
  return { kind, ...(k?.defaults || {}) };
}

// Apply a user preset: same as the kind it's built on + its overrides.
function makeJoinerFromPreset(preset) {
  return { kind: preset.builtOn, ...preset.params };
}

// ── Animated joiner preview ──────────────────────────────────────
// Plays the transition on loop. Two stand-in "clips" — left and right
// — come from the segments adjacent to this joiner (prevClip ends a
// section, nextClip starts this section). Falls back to colored panels
// if no thumbs are provided.
function AnimatedJoinerPreview({ joiner, prevClip, nextClip }) {
  const [playing, setPlaying] = jeState(true);
  const [tNorm, setTNorm] = jeState(0); // 0..1 progress through the transition
  const rafRef = jeRef();
  const lastTickRef = jeRef();
  const totalMs = Math.max(400, FA_DATA.joinerTotalMs(joiner));
  // Include 600ms of "lead-in" + "lead-out" on either side so the
  // viewer sees a moment of each clip before the transition starts.
  const padMs = 600;
  const loopMs = padMs + totalMs + padMs;

  jeUseEffect(() => {
    if (!playing) return;
    lastTickRef.current = performance.now();
    function tick(now) {
      const dt = now - (lastTickRef.current || now);
      lastTickRef.current = now;
      setTNorm(t => {
        const next = t + (dt / loopMs);
        return next >= 1 ? 0 : next; // loop
      });
      rafRef.current = requestAnimationFrame(tick);
    }
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [playing, loopMs]);

  // Convert tNorm (loop position) into transition-local progress.
  // Returns {phase, t} where phase ∈ {"prevLead","transition","nextLead"}.
  function phaseAt(tNorm) {
    const ms = tNorm * loopMs;
    if (ms < padMs) return { phase: "prevLead", t: ms / padMs };
    if (ms < padMs + totalMs) return { phase: "transition", t: (ms - padMs) / totalMs };
    return { phase: "nextLead", t: (ms - padMs - totalMs) / padMs };
  }
  const { phase, t } = phaseAt(tNorm);

  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
                     marginBottom: 6 }}>
        <span style={{ fontSize: 10.5, fontWeight: 700, color: "var(--text-dim)",
                        textTransform: "uppercase", letterSpacing: "0.1em" }}>
          Animated preview
        </span>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span className="mono" style={{ fontSize: 10.5, color: "var(--text-dim)" }}>
            {phase === "transition"
              ? `${(t * totalMs / 1000).toFixed(1)}s / ${(totalMs / 1000).toFixed(1)}s`
              : (phase === "prevLead" ? "before" : "after")}
          </span>
          <Button kind="ghost" size="icon" title={playing ? "Pause" : "Play"}
                   onClick={() => setPlaying(p => !p)}>
            <Icon name={playing ? "pause" : "play"} size={12} />
          </Button>
          <Button kind="ghost" size="icon" title="Restart"
                   onClick={() => { setTNorm(0); setPlaying(true); }}>
            <Icon name="rotate-ccw" size={12} />
          </Button>
        </div>
      </div>

      <div style={{
        position: "relative", width: "100%", aspectRatio: "16 / 9",
        background: "#000", borderRadius: 6, overflow: "hidden",
        border: "1px solid var(--border)",
      }}>
        {renderJoinerFrame({ joiner, prevClip, nextClip, phase, t })}
      </div>

      {/* Transition timeline scrub */}
      <div style={{ position: "relative", height: 8, marginTop: 8 }}>
        <span style={{
          position: "absolute", inset: 0, height: 2, top: 3,
          background: "var(--border)", borderRadius: 1,
        }} />
        {/* highlight transition window */}
        <span style={{
          position: "absolute", top: 3, height: 2, borderRadius: 1,
          left:  `${(padMs / loopMs) * 100}%`,
          right: `${(padMs / loopMs) * 100}%`,
          background: "rgba(255,140,66,0.5)",
        }} />
        {/* playhead */}
        <span style={{
          position: "absolute", top: 0, left: `${tNorm * 100}%`, transform: "translateX(-50%)",
          width: 2, height: 8, background: "var(--accent)", borderRadius: 1,
          boxShadow: "0 0 6px rgba(255,75,75,0.5)",
        }} />
      </div>
    </div>
  );
}

// Render one frame of the transition at progress t inside the given phase.
// Returns JSX nodes layered absolutely inside the preview frame.
function renderJoinerFrame({ joiner, prevClip, nextClip, phase, t }) {
  const prevSrc = prevClip?.thumb;
  const nextSrc = nextClip?.thumb;

  // Phase-based outer layer logic — within the transition window, the
  // joiner kind drives what happens. Outside, we just show the
  // appropriate static clip.
  if (phase === "prevLead") return <ClipPanel src={prevSrc} label="previous clip" tint="left" />;
  if (phase === "nextLead") return <ClipPanel src={nextSrc} label="next clip" tint="right" />;

  // ── Inside the transition ─────────────────────────────────────
  const k = joiner.kind;
  if (k === "none") {
    // Instant cut at t=0; show prev for t<0.5 and next after.
    return <ClipPanel src={t < 0.5 ? prevSrc : nextSrc}
                       label={t < 0.5 ? "previous clip" : "next clip"}
                       tint={t < 0.5 ? "left" : "right"} />;
  }
  if (k === "fade_through_black" || k === "dip_to_color") {
    const fo = joiner.fadeOutS || 0;
    const ho = joiner.holdS    || 0;
    const fi = joiner.fadeInS  || 0;
    const tot = Math.max(0.01, fo + ho + fi);
    const cur = t * tot; // seconds into transition
    const color = joiner.color || "#000000";
    // Phase opacities
    let leftOp = 0, rightOp = 0, holdOp = 0;
    if (cur < fo) {
      const x = cur / fo;            // 0 → 1
      leftOp = 1 - x; holdOp = x;
    } else if (cur < fo + ho) {
      leftOp = 0; holdOp = 1; rightOp = 0;
    } else {
      const x = (cur - fo - ho) / fi; // 0 → 1
      holdOp = 1 - x; rightOp = x;
    }
    return (
      <>
        {leftOp > 0 && <ClipPanel src={prevSrc} label="previous clip" tint="left" opacity={leftOp} />}
        {rightOp > 0 && <ClipPanel src={nextSrc} label="next clip" tint="right" opacity={rightOp} />}
        <span style={{ position: "absolute", inset: 0, background: color, opacity: holdOp }} />
      </>
    );
  }
  if (k === "crossfade") {
    // Linear cross-dissolve. (Easing curves omitted for the preview.)
    return (
      <>
        <ClipPanel src={prevSrc} label="previous clip" tint="left" opacity={1 - t} />
        <ClipPanel src={nextSrc} label="next clip" tint="right" opacity={t} />
      </>
    );
  }
  if (k === "swipe") {
    const dir = joiner.direction || "ltr";
    const soft = (joiner.softness || 0);
    // Compute a clip-path inset for the next clip based on direction.
    // softness = % feather along the moving edge (rendered as a stop softness).
    const pct = Math.max(0, Math.min(100, t * 100));
    let mask;
    if (dir === "ltr")      mask = `linear-gradient(90deg, #fff ${pct - soft / 2}%, transparent ${pct + soft / 2}%)`;
    else if (dir === "rtl") mask = `linear-gradient(270deg, #fff ${pct - soft / 2}%, transparent ${pct + soft / 2}%)`;
    else if (dir === "ttb") mask = `linear-gradient(180deg, #fff ${pct - soft / 2}%, transparent ${pct + soft / 2}%)`;
    else                    mask = `linear-gradient(0deg,   #fff ${pct - soft / 2}%, transparent ${pct + soft / 2}%)`;
    return (
      <>
        <ClipPanel src={prevSrc} label="previous clip" tint="left" />
        <div style={{
          position: "absolute", inset: 0,
          WebkitMaskImage: mask, maskImage: mask,
        }}>
          <ClipPanel src={nextSrc} label="next clip" tint="right" />
        </div>
      </>
    );
  }
  return <ClipPanel src={prevSrc} label="previous clip" tint="left" />;
}

// Pretty fallback when no real thumb is available. Uses FunscriptForge's
// VideoPoster motif so the clip panels match the rest of the app's
// look-and-feel.
function ClipPanel({ src, label, tint, opacity = 1 }) {
  return (
    <div style={{
      position: "absolute", inset: 0, opacity,
      background: "linear-gradient(135deg, #16181d 0%, #1f242c 100%)",
    }}>
      {src
        ? <img src={src} alt="" style={{
            position: "absolute", inset: 0, width: "100%", height: "100%",
            objectFit: "cover", display: "block",
          }} />
        : (window.VideoPoster
            ? <window.VideoPoster title={label} />
            : null)}
      <div style={{ position: "absolute", top: 8, left: 10,
                     fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 700,
                     letterSpacing: "0.08em", textTransform: "uppercase",
                     color: "rgba(255,255,255,0.78)" }}>
        {label}
      </div>
    </div>
  );
}

function JoinerEditor({ joiner, userJoiners, prevClip, nextClip, anchorRect, onChange, onClose, onSaveAsPreset }) {
  const ref = jeRef();
  const kind = FA_DATA.joinerKind(joiner);

  // Position above the anchor when there's room; otherwise below.
  const pos = anchorRect ? computePos(anchorRect) : { top: 80, left: 80 };

  // Close on outside click.
  jeUseEffect(() => {
    function onDown(e) { if (ref.current && !ref.current.contains(e.target)) onClose(); }
    window.addEventListener("mousedown", onDown);
    return () => window.removeEventListener("mousedown", onDown);
  }, [onClose]);

  // re-run lucide icons after render
  jeUseEffect(() => { window.lucide?.createIcons?.(); });

  function setParam(id, v) { onChange({ ...joiner, [id]: v }); }
  function setKind(newKind) { onChange(makeJoinerFromKind(newKind)); }
  function applyPreset(p) { onChange(makeJoinerFromPreset(p)); }

  return (
    <div ref={ref} style={{
      position: "fixed", top: pos.top, left: pos.left, zIndex: 30,
      width: 380, maxHeight: "70vh", overflow: "auto",
      background: "var(--surface)", border: "1px solid var(--border)",
      borderRadius: 10, boxShadow: "var(--elev-3)",
      display: "flex", flexDirection: "column",
    }}>
      {/* Header */}
      <div style={{ padding: "12px 14px", borderBottom: "1px solid var(--border)",
                     display: "flex", alignItems: "center", gap: 10 }}>
        <Icon name={kind.icon} size={15} style={{ color: kind.kind === "none" ? "var(--text-muted)" : "var(--accent-warm)" }} />
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 12.5, fontWeight: 600 }}>Joiner</div>
          <div style={{ fontSize: 11, color: "var(--text-dim)" }}>How this section transitions in</div>
        </div>
        <Button kind="ghost" size="icon" onClick={onClose}><Icon name="x" size={14} /></Button>
      </div>

      {/* Kind picker */}
      <div style={{ padding: 12, borderBottom: "1px solid var(--border)" }}>
        <span style={{ fontSize: 10.5, fontWeight: 700, color: "var(--text-dim)",
                        textTransform: "uppercase", letterSpacing: "0.1em" }}>Type</span>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginTop: 8 }}>
          {FA_DATA.JOINER_KINDS.map(k => {
            const active = joiner.kind === k.kind;
            return (
              <button key={k.kind} onClick={() => setKind(k.kind)} style={{
                display: "inline-flex", alignItems: "center", gap: 5,
                padding: "5px 10px", borderRadius: 6,
                background: active ? "rgba(255,75,75,0.08)" : "var(--surface-2)",
                border: `1px solid ${active ? "var(--accent)" : "var(--border)"}`,
                color: active ? "var(--text)" : "var(--text-muted)",
                fontFamily: "inherit", fontSize: 11.5, fontWeight: 600, cursor: "pointer",
              }}>
                <Icon name={k.icon} size={11} /> {k.label}
              </button>
            );
          })}
        </div>
        {/* user presets */}
        {userJoiners?.length > 0 && (
          <>
            <div style={{ marginTop: 12, display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ fontSize: 10.5, fontWeight: 700, color: "var(--text-dim)",
                              textTransform: "uppercase", letterSpacing: "0.1em" }}>Your joiners</span>
              <Pill style={{ fontSize: 9 }}>{userJoiners.length}</Pill>
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginTop: 8 }}>
              {userJoiners.map(p => {
                const builtOn = FA_DATA.JOINER_KINDS.find(k => k.kind === p.builtOn);
                return (
                  <button key={p.id} onClick={() => applyPreset(p)} style={{
                    display: "inline-flex", alignItems: "center", gap: 5,
                    padding: "5px 10px", borderRadius: 6,
                    background: "var(--surface-2)", border: "1px solid var(--border)",
                    color: "var(--text)", fontFamily: "inherit", fontSize: 11.5, fontWeight: 600,
                    cursor: "pointer",
                  }}>
                    <Icon name={builtOn?.icon || "bookmark"} size={11}
                          style={{ color: "var(--accent-warm)" }} />
                    {p.name}
                  </button>
                );
              })}
            </div>
          </>
        )}
      </div>

      {/* Description */}
      <div style={{ padding: "10px 14px", fontSize: 11.5, color: "var(--text-muted)",
                     lineHeight: 1.5, borderBottom: "1px solid var(--border)" }}>
        {kind.desc}
      </div>

      {/* Params */}
      {joiner.kind !== "none" && (
        <div style={{ padding: 14 }}>
          {/* Animated preview at the top — loops the transition */}
          <AnimatedJoinerPreview joiner={joiner}
                                  prevClip={prevClip} nextClip={nextClip} />

          {/* Timeline visualisation for fade-style joiners */}
          {(joiner.kind === "fade_through_black" || joiner.kind === "dip_to_color") && (
            <TimingVisual joiner={joiner} kind={kind} />
          )}

          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {kind.params.map(p => (
              <ParamControl key={p.id} param={p}
                             value={joiner[p.id] ?? p.default}
                             onChange={(v) => setParam(p.id, v)} />
            ))}
          </div>
        </div>
      )}

      {/* Footer */}
      <div style={{ padding: "10px 14px", borderTop: "1px solid var(--border)",
                     display: "flex", alignItems: "center", gap: 8 }}>
        {joiner.kind !== "none" && (
          <Button kind="ghost" size="sm" icon="bookmark-plus"
                  onClick={() => onSaveAsPreset(joiner)}>
            Save as preset…
          </Button>
        )}
        <div style={{ flex: 1 }} />
        <span className="mono" style={{ fontSize: 10.5, color: "var(--text-dim)" }}>
          total {(FA_DATA.joinerTotalMs(joiner) / 1000).toFixed(2)}s
        </span>
        <Button kind="primary" size="sm" onClick={onClose}>Done</Button>
      </div>
    </div>
  );
}

// Position the popover ~ above the anchor, clamped to viewport.
function computePos(rect) {
  const w = 380;
  const margin = 16;
  let left = rect.left + rect.width / 2 - w / 2;
  left = Math.max(margin, Math.min(window.innerWidth - w - margin, left));
  let top = rect.top - 16;
  // If too high, place below
  if (top < margin + 200) top = Math.min(window.innerHeight - 320, rect.bottom + 8);
  else top = top - 200; // rough panel height
  return { top, left };
}

// ── Timing visual for fade-style joiners ─────────────────────────
function TimingVisual({ joiner, kind }) {
  const fo = joiner.fadeOutS || 0;
  const ho = joiner.holdS    || 0;
  const fi = joiner.fadeInS  || 0;
  const total = Math.max(0.01, fo + ho + fi);
  const c = joiner.color || "#000";

  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10,
                     color: "var(--text-dim)", fontFamily: "var(--font-mono)",
                     letterSpacing: "0.06em", textTransform: "uppercase",
                     marginBottom: 4 }}>
        <span>prev clip</span>
        <span style={{ color: "var(--accent-warm)" }}>{kind.label}</span>
        <span>next clip</span>
      </div>
      <div style={{ display: "flex", height: 32, gap: 1,
                     border: "1px solid var(--border)", borderRadius: 4, overflow: "hidden" }}>
        <div style={{
          width: `${(fo / total) * 100}%`,
          background: `linear-gradient(90deg, var(--surface-3, #232735), ${c})`,
        }} title="Fade out" />
        <div style={{
          width: `${(ho / total) * 100}%`, background: c,
        }} title="Hold" />
        <div style={{
          width: `${(fi / total) * 100}%`,
          background: `linear-gradient(90deg, ${c}, var(--surface-3, #232735))`,
        }} title="Fade in" />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between",
                     fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-muted)",
                     marginTop: 4 }}>
        <span>{fo.toFixed(1)}s fade out</span>
        <span style={{ color: ho > 0 ? "var(--text)" : "var(--text-dim)" }}>{ho.toFixed(1)}s hold</span>
        <span>{fi.toFixed(1)}s fade in</span>
      </div>
    </div>
  );
}

// ── Generic param control ────────────────────────────────────────
function ParamControl({ param, value, onChange }) {
  if (param.kind === "time" || param.kind === "range") {
    return (
      <Slider value={value} min={param.min} max={param.max} step={param.step}
              onChange={onChange}
              label={param.label}
              valueLabel={`${typeof value === "number" ? value.toFixed(param.step < 1 ? 1 : 0) : value}${param.unit || ""}`} />
    );
  }
  if (param.kind === "enum") {
    // For short option lists use segmented; longer go to a wrap.
    return (
      <Field label={param.label}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
          {param.options.map(o => {
            const active = value === o;
            return (
              <button key={o} onClick={() => onChange(o)} style={{
                padding: "4px 10px", borderRadius: 5,
                background: active ? "var(--accent)" : "var(--surface-2)",
                border: `1px solid ${active ? "var(--accent)" : "var(--border)"}`,
                color: active ? "#fff" : "var(--text-muted)",
                fontFamily: "inherit", fontSize: 11, fontWeight: 600, cursor: "pointer",
                fontVariantNumeric: "tabular-nums",
              }}>
                {o}
              </button>
            );
          })}
        </div>
      </Field>
    );
  }
  if (param.kind === "color") {
    return (
      <Field label={param.label}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <input type="color" value={value} onChange={(e) => onChange(e.target.value)}
                  style={{ width: 32, height: 28, border: "1px solid var(--border)",
                            background: "var(--surface-2)", borderRadius: 4, padding: 2, cursor: "pointer" }} />
          <TextInput value={value} mono onChange={onChange} style={{ flex: 1 }} />
          <div style={{ display: "flex", gap: 4 }}>
            {["#000000", "#fafafa", "#ff4b4b", "#ff8c42", "#1a0e1e"].map(c => (
              <button key={c} onClick={() => onChange(c)} title={c}
                       style={{ width: 18, height: 18, borderRadius: 3,
                                 background: c, border: "1px solid var(--border)",
                                 cursor: "pointer" }} />
            ))}
          </div>
        </div>
      </Field>
    );
  }
  return null;
}

// ── Save-as-preset prompt (lightweight inline form) ──────────────
function SavePresetPrompt({ joiner, onSave, onCancel }) {
  const [name, setName] = jeState("");
  const kind = FA_DATA.joinerKind(joiner);
  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 40,
      background: "rgba(0,0,0,0.65)",
      display: "grid", placeItems: "center",
    }} onClick={onCancel}>
      <div onClick={(e) => e.stopPropagation()} style={{
        width: 420, background: "var(--surface)", border: "1px solid var(--border)",
        borderRadius: 10, padding: 18, display: "flex", flexDirection: "column", gap: 14,
        boxShadow: "var(--elev-3)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Icon name="bookmark-plus" size={16} style={{ color: "var(--accent-warm)" }} />
          <span style={{ fontSize: 14, fontWeight: 600 }}>Save joiner as preset</span>
        </div>
        <div style={{ fontSize: 11.5, color: "var(--text-muted)", lineHeight: 1.5 }}>
          Builds on <strong style={{ color: "var(--text)" }}>{kind.label}</strong>.
          Your preset will appear in the Joiner picker and on the Joiners tab.
        </div>
        <Field label="Name">
          <TextInput value={name} onChange={setName} placeholder="e.g. Quick fade · 0.4s" />
        </Field>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <Button kind="ghost" size="sm" onClick={onCancel}>Cancel</Button>
          <Button kind="primary" size="sm" disabled={!name.trim()}
                  onClick={() => onSave(name.trim())}>Save preset</Button>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { JoinerEditor, SavePresetPrompt, makeJoinerFromKind, makeJoinerFromPreset });


export { AnimatedJoinerPreview, ClipPanel, JoinerEditor, ParamControl, SavePresetPrompt, TimingVisual, computePos, makeJoinerFromKind, makeJoinerFromPreset, renderJoinerFrame };
