/* @esm-converted */
import React from 'react';
const { useState, useEffect } = React;
import { FASectionLabel, FATabBody, FATabHeader, fmtTotal } from './AppShell';
import { ParamControl, TimingVisual } from './JoinerEditor';
import { FA_DATA } from './data';
import { pickFile, probeMedia, videoEncoder } from './api/forge';
import { Button, Card, Field, Icon, Pill, Segmented, Slider, TextInput } from './primitives';
import { Modal, ModalFooter } from './ProjectIO';
import { effectiveDurMs, funscriptRelPath, projectChannelCoverage,
         renderTag, renderedVideoName, segmentHasChannel } from './lib/projectAdapter';
import { projectFileName } from './lib/projectFile';

// Sketched other pipeline tabs. Intentionally light — the Build tab is
// where the design work is concentrated; these convey the structure
// and the chain pattern.

// ── Project tab removed ───────────────────────────────────────────
// Was a dead form (basename/output-folder now set via Save As; recent
// projects + New/Open moved to the Home screen — see HomeScreen.jsx).
// The two real "Produce" toggles folded into the Output tab below.

// ── Channels tab removed — folded into Output. Detection-driven now.

// ── Output tab (also absorbs channel coverage) ───────────────────
// Channels aren't opt-in: detection decides what exists, and the switches
// here only ever SUBTRACT a group from that. Gaps (a channel one clip
// lacks) are left blank — the engine has no fallback synthesis, and the
// picker that used to offer one wasn't wired to anything.
// A new overlay's resting state. The engine's own defaults, spelled out
// here because a form with empty boxes is worse than one with sane values
// -- and `duration_s: 0` is meaningful: run to the end.
function newOverlay(kind) {
  return {
    id: `ov-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
    kind,
    file: "",
    start_s: 0,
    duration_s: 0,
    fade_in_s: 0,
    fade_out_s: 0,
    position: kind === "text" ? "bc" : "br",
    opacity: 1.0,
    scale_pct: 100,
    text: "",
    text_color: "#ffffff",
    font_size: 48,
  };
}

function OutputTab({ project, onSetOutput, onSetChannels,
                     onPickBranding, onClearBranding, onSetOverlays }) {
  const out = project.output || {};
  const chans = project.channels || {};
  // { index, draft } while the dialog is open; index -1 means "new".
  const [editing, setEditing] = useState(null);
  return (
    <FATabBody>
      <FATabHeader
        eyebrow="Pipeline · 02 of 03"
        title="Output settings"
        subtitle="What to produce, resolution, frame rate, bug overlay, audio normalisation, and what to do about partially-covered funscript channels — all applied once across the whole combined output."
      />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <Card>
          <FASectionLabel>Produce</FASectionLabel>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <Toggle label="Video (MP4)" checked={out.video !== false}
                    onChange={(v) => onSetOutput?.({ video: v })} />
            <Toggle label="Funscripts" checked={out.funscripts !== false}
                    onChange={(v) => onSetOutput?.({ funscripts: v })} />
            <Toggle label="Haptic-estim audio (WAV)" checked={!!chans.audio_estim}
                    onChange={(v) => onSetChannels?.({ audio_estim: v })} />
            <Toggle label=".forge scene" checked={out.forgeBundle !== false}
                    onChange={(v) => onSetOutput?.({ forgeBundle: v })} />
            {out.forgeBundle !== false && (
              <div style={{ paddingLeft: 22 }}>
                <Toggle label="…with the video inside it"
                        checked={!!out.forgeBundleMedia}
                        onChange={(v) => onSetOutput?.({ forgeBundleMedia: v })} />
              </div>
            )}
          </div>
          <div style={{ marginTop: 10, padding: "8px 10px", background: "var(--surface-2)",
                         border: "1px solid var(--border)", borderRadius: 6,
                         fontSize: 11, color: "var(--text-muted)" }}>
            Chapter markers are always written when video is produced.
            {out.forgeBundle !== false && (
              <>
                <br />
                The <span className="mono">.forge</span> scene packs every channel, the
                joined analysis and this compilation's chapters into one file —
                re-openable in FunscriptForge, playable in ForgePlayer.
                {out.forgeBundleMedia
                  ? " Including the video makes it as big as the MP4."
                  : " It references the MP4 rather than carrying it."}
              </>
            )}
          </div>
        </Card>
        <Card>
          <FASectionLabel>Branding</FASectionLabel>
          <div style={{ marginBottom: 10, fontSize: 11, color: "var(--text-dim)", lineHeight: 1.5 }}>
            Optional <span className="mono">.forge</span> scenes at each end.
            They bring their own audio and funscripts, so an intro doubles as a
            calibration run before any content plays. Neither becomes a
            chapter — chapter 01 stays your first scene.
          </div>
          <BrandingSlot which="intro" label="Before the compilation"
                         seg={project.output?.brandingIntro}
                         onPick={onPickBranding} onClear={onClearBranding} />
          <BrandingSlot which="outro" label="After the compilation"
                         seg={project.output?.brandingOutro}
                         onPick={onPickBranding} onClear={onClearBranding} />
        </Card>
        <OverlaysCard overlays={project.output?.overlays || []}
                      onAdd={(kind) => setEditing({ index: -1, draft: newOverlay(kind) })}
                      onEdit={(i) => setEditing({ index: i, draft: (project.output.overlays || [])[i] })}
                      onRemove={(i) => onSetOverlays?.(
                        (project.output?.overlays || []).filter((_, j) => j !== i))} />
        <Card>
          <FASectionLabel>Resolution</FASectionLabel>
          <ResolutionPicker value={project.output.resolution}
                             onChange={(v) => onSetOutput?.({ resolution: v })} />
        </Card>
        <Card>
          <FASectionLabel>Quality &amp; frame rate</FASectionLabel>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <Field label="Quality">
              <Segmented value={out.quality || "medium"}
                          onChange={(v) => onSetOutput?.({ quality: v })}
                          options={[
                            { value: "low", label: "Low · CRF 28" },
                            { value: "medium", label: "Medium · CRF 23" },
                            { value: "high", label: "High · CRF 18" },
                          ]} />
            </Field>
            <Field label="Frame rate">
              <Segmented value={out.frameRate || "source"}
                          onChange={(v) => onSetOutput?.({ frameRate: v })}
                          options={[
                            { value: "source", label: "Source" },
                            { value: "24", label: "24" },
                            { value: "30", label: "30" },
                            { value: "60", label: "60" },
                          ]} />
            </Field>
          </div>
        </Card>
        <Card>
          <FASectionLabel>Audio</FASectionLabel>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <Toggle label="Normalize audio loudness · −16 LUFS" checked={!!out.normalizeAudio}
                    onChange={(v) => onSetOutput?.({ normalizeAudio: v })} />
            <div style={{ padding: "8px 10px", background: "var(--surface-2)",
                            border: "1px solid var(--border)", borderRadius: 6,
                            fontSize: 11, color: "var(--text-muted)", marginTop: 8 }}>
              Audio beds can be placed on the Build canvas and are saved with the
              project, but the forge doesn't mix them into the output yet.
            </div>
          </div>
        </Card>
        <BugOverlayCard bug={out.bug} onSetOutput={onSetOutput} />
      </div>

      <div style={{ marginTop: 20 }}>
        <OutputChannelsCard project={project} onSetChannels={onSetChannels} />
      </div>

      {editing && (
        <OverlayDialog
          overlay={editing.draft}
          hasOutro={!!project.output?.brandingOutro}
          onClose={() => setEditing(null)}
          onSave={(next) => {
            const list = [...(project.output?.overlays || [])];
            if (editing.index < 0) list.push(next);
            else list[editing.index] = next;
            onSetOverlays?.(list);
            setEditing(null);
          }} />
      )}
    </FATabBody>
  );
}

// ── Bug overlay card ─────────────────────────────────────────────
// A PNG composited into one corner of every clip. `Output.bug` is a real
// schema field the video pipeline implements (filters.corner_position_expr);
// this card used to be a hardcoded sketch with no state, so the setting
// could never be made — and, until the adapter carried it, a project that
// already had one lost it the first time the GUI saved.
function BugOverlayCard({ bug, onSetOutput }) {
  async function pickBug() {
    const file = await pickFile({
      title: "Choose the bug PNG", filterName: "PNG image", extensions: ["png"],
    });
    if (!file) return;
    onSetOutput?.({ bug: { corner: "br", margin_px: 24, opacity: 1.0, ...(bug || {}), file } });
  }
  const set = (patch) => onSetOutput?.({ bug: { ...bug, ...patch } });

  return (
    <Card>
      <FASectionLabel right={
        bug
          ? <Button kind="ghost" size="sm" icon="x"
                     onClick={() => onSetOutput?.({ bug: null })}>Remove</Button>
          : <Button kind="ghost" size="sm" icon="plus" onClick={pickBug}>Add bug</Button>
      }>
        Bug overlay
      </FASectionLabel>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <Field label="PNG file">
          <div style={{ display: "flex", gap: 6 }}>
            <TextInput value={bug?.file || ""} mono readOnly
                        placeholder="None — click Add bug to pick a PNG" />
            {bug && <Button kind="secondary" size="sm" onClick={pickBug}>Change…</Button>}
          </div>
        </Field>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          <Field label="Corner">
            <Segmented value={bug?.corner || "br"} disabled={!bug}
                        onChange={(v) => set({ corner: v })}
                        options={[{ value: "tl", label: "TL" }, { value: "tr", label: "TR" },
                                  { value: "bl", label: "BL" }, { value: "br", label: "BR" }]} />
          </Field>
          <Field label="Margin">
            <Slider value={bug?.margin_px ?? 24} min={0} max={200} step={4} disabled={!bug}
                    onChange={(v) => set({ margin_px: Math.round(v) })}
                    valueLabel={`${bug?.margin_px ?? 24} px`} />
          </Field>
        </div>
        <Slider value={Math.round((bug?.opacity ?? 1) * 100)} min={0} max={100} step={5}
                label="Opacity" disabled={!bug}
                valueLabel={`${Math.round((bug?.opacity ?? 1) * 100)}%`}
                onChange={(v) => set({ opacity: v / 100 })} />
      </div>
    </Card>
  );
}

// ── Output channels card (was its own tab) ───────────────────
// Reports what the forge will ACTUALLY write. The engine is
// detection-driven: every channel found on the clips is produced, and
// the group switches here are vetoes over that. A real FunscriptForge
// scene carries ~20 channels — ten categorised, the rest device and
// restim-parameter tracks — so this card reads them off the clips
// rather than off a fixed menu, which used to report a 20-channel
// scene as "2D main".
function OutputChannelsCard({ project, onSetChannels }) {
  const cov = projectChannelCoverage(project);
  const estimClips = project.sections.flatMap(s => s.segments)
    .filter(s => s.kind !== "still");
  const estimHave = estimClips.filter(s => segmentHasChannel(s, "audio_estim")).length;
  const produceEstim = project.channels?.audio_estim !== false;

  return (
    <Card padding={18}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 14, marginBottom: 14 }}>
        <Icon name="layers" size={18} style={{ color: "var(--accent-warm)", marginTop: 1 }} />
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>Output channels</div>
          <div style={{ fontSize: 12, color: "var(--text-muted)", lineHeight: 1.5, maxWidth: 720 }}>
            Every funscript channel found on your clips is forged — you don't opt in. Where a
            channel is missing from a clip, that stretch of the combined script is left blank,
            so the channels that <em>are</em> there stay in lockstep with the video.
          </div>
        </div>
        <Pill tone="accent" style={{ fontSize: 10 }}>
          {cov.detected} channel{cov.detected === 1 ? "" : "s"}
        </Pill>
      </div>

      {cov.clips === 0 ? (
        <div style={{ padding: "18px 14px", borderRadius: 8, textAlign: "center",
                       background: "var(--surface-2)", border: "1px dashed var(--border)",
                       fontSize: 12, color: "var(--text-dim)" }}>
          No clips yet. Add a <span className="mono">.forge</span> scene on the Build tab and its
          channels appear here.
        </div>
      ) : cov.groups.length === 0 ? (
        <div style={{ padding: "18px 14px", borderRadius: 8, textAlign: "center",
                       background: "var(--surface-2)", border: "1px dashed var(--border)",
                       fontSize: 12, color: "var(--text-dim)" }}>
          None of the {cov.clips} clip{cov.clips === 1 ? "" : "s"} carries a funscript, so there's
          nothing to forge on the haptic side.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {cov.groups.map(g => (
            <ChannelGroupRow key={g.id} group={g} clips={cov.clips}
                              onToggle={g.veto
                                ? (on) => onSetChannels({ [g.veto]: on })
                                : null} />
          ))}
        </div>
      )}

      {/* Haptic e-stim audio is a separate artifact (one file per channel),
          not a sub-channel of the funscript output — hence its own row and
          its own produce flag. */}
      {estimClips.length > 0 && (
        <div style={{ marginTop: 12, display: "flex", alignItems: "center", gap: 14,
                       padding: "10px 12px", borderRadius: 8,
                       background: "var(--surface-2)", border: "1px solid var(--border)" }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 12.5, fontWeight: 600 }}>Haptic e-stim audio</div>
            <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>
              {estimHave === 0
                ? "No clip carries e-stim audio."
                : `Carried by ${estimHave} of ${estimClips.length} clip${estimClips.length === 1 ? "" : "s"}` +
                  (estimHave === estimClips.length ? "." : " — silence elsewhere.")}
            </div>
          </div>
          <Segmented value={produceEstim ? "on" : "off"}
                      onChange={(v) => onSetChannels({ audio_estim: v === "on" })}
                      options={[{ value: "on", label: "Produce" },
                                { value: "off", label: "Skip" }]} />
        </div>
      )}
    </Card>
  );
}

// One channel group: its switch, and a compact line per member channel
// showing how many clips carry it. Partial coverage is the thing worth
// seeing — it's exactly where the combined script goes quiet.
function ChannelGroupRow({ group, clips, onToggle }) {
  const partial = group.channels.filter(c => !c.full);
  const off = !group.included;
  return (
    <div style={{ padding: "10px 12px", borderRadius: 8,
                   background: "var(--surface-2)",
                   border: "1px solid var(--border)",
                   opacity: off ? 0.55 : 1 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 12.5, fontWeight: 600 }}>
            {group.label}
            <span style={{ fontWeight: 400, color: "var(--text-dim)", marginLeft: 8 }}>
              {group.channels.length} channel{group.channels.length === 1 ? "" : "s"}
            </span>
          </div>
          <div style={{ fontSize: 11, color: off ? "var(--text-dim)" : "var(--text-muted)", marginTop: 2 }}>
            {off
              ? "Skipped — not written to the output."
              : partial.length === 0
                ? "On every clip — continuous across the whole compilation."
                : `Blank where missing: ${partial.map(c => c.channel || c.id).join(", ")}.`}
          </div>
        </div>
        {onToggle ? (
          <Segmented value={group.included ? "on" : "off"}
                      onChange={(v) => onToggle(v === "on")}
                      options={[{ value: "on", label: "Forge" },
                                { value: "off", label: "Skip" }]} />
        ) : (
          <Pill tone="neutral" style={{ fontSize: 10 }}>always</Pill>
        )}
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
        {/* The station has to show. Three of these rows can read `alpha` —
            estim3p, focstim and focstim4p each write their own, clamped for
            their own hardware — so the channel name alone names no file. */}
        {group.channels.map(c => (
          <span key={c.id} className="mono"
                 title={`${c.have} of ${c.eligible} clips`
                        + (c.stationLabel ? ` · ${c.stationLabel}` : "")}
                 style={{ fontSize: 10.5, padding: "2px 7px", borderRadius: 5,
                          border: `1px solid ${c.full ? "var(--border)" : "var(--warn)"}`,
                          color: c.full ? "var(--text-muted)" : "var(--warn)",
                          background: "var(--bg)" }}>
            {c.channel || c.id}
            {c.stationLabel && (
              <span style={{ marginLeft: 5, opacity: 0.7 }}>{c.stationLabel}</span>
            )}
            {!c.full && <span style={{ marginLeft: 5 }}>{c.have}/{c.eligible}</span>}
          </span>
        ))}
      </div>
    </div>
  );
}

function ResolutionPicker({ value, onChange }) {
  const groups = [
    { title: "16:9 widescreen", opts: [
      { v: "1080p",     label: "1080p",   px: "1920×1080" },
      { v: "1440p",     label: "1440p",   px: "2560×1440" },
      { v: "4k",        label: "4K",      px: "3840×2160" },
    ]},
    { title: "21:9 cinematic", opts: [
      { v: "uw_1080p",  label: "UW 1080p", px: "2560×1080" },
      { v: "uw_1440p",  label: "UW 1440p", px: "3440×1440" },
    ]},
    { title: "4:3 / vertical", opts: [
      { v: "4_3_hd",    label: "4:3 HD",   px: "1440×1080" },
      { v: "3_4_hd",    label: "3:4",      px: "1080×1440" },
      { v: "9_16_hd",   label: "9:16",     px: "1080×1920" },
    ]},
    { title: "Source", opts: [
      { v: "source",    label: "Source",   px: "first clip" },
    ]},
  ];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {groups.map(g => (
        <div key={g.title}>
          <span className="mono" style={{ fontSize: 10.5, color: "var(--text-dim)",
                                            textTransform: "uppercase", letterSpacing: "0.08em" }}>
            {g.title}
          </span>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}>
            {g.opts.map(o => {
              const on = o.v === value;
              return (
                <button key={o.v} onClick={() => onChange?.(o.v)} style={{
                  display: "flex", flexDirection: "column", alignItems: "flex-start",
                  padding: "6px 12px", borderRadius: 6,
                  background: on ? "rgba(255,75,75,0.08)" : "var(--surface-2)",
                  border: `1px solid ${on ? "var(--accent)" : "var(--border)"}`,
                  color: on ? "var(--text)" : "var(--text-muted)",
                  cursor: "pointer", fontFamily: "inherit",
                }}>
                  <span style={{ fontSize: 12, fontWeight: 600 }}>{o.label}</span>
                  <span className="mono" style={{ fontSize: 10, color: "var(--text-dim)" }}>{o.px}</span>
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Forge tab ─────────────────────────────────────────────────────
function ForgeTab({ project, totalMs, onForge, onCancelForge, cancelling,
                    forging, progress, forgeStage }) {
  // What the forge will write, counted the same way the engine counts it.
  const flat = project.sections.flatMap(s => s.segments);
  const cov = projectChannelCoverage(project);
  // Resolve `source` rather than repeat it back, so the rows below can name
  // a real frame rate and a real filename.
  const { fps, source: fpsFromSource } = useEffectiveFps(project);
  const tag = fps == null ? null : renderTag(project.output?.resolution, fps);
  const videoName = tag ? `${project.name}.${tag}.mp4` : null;

  return (
    <FATabBody>
      <FATabHeader
        eyebrow="Pipeline · 03 of 03"
        title="Forge"
        subtitle="One pass. ForgeAssembler concatenates the videos, the funscript channels in lockstep, and writes chapter markers for every section boundary."
      />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <Card>
          <FASectionLabel>Summary</FASectionLabel>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
            <tbody>
              {[
                ["Scenes",        flat.length],
                ["Chapters",      flat.length],
                ["Total duration", fmtTotal(totalMs)],
                ["Resolution",    project.output.resolution],
                // Always a number when we can get one. "source" answers a
                // different question than "what am I about to render".
                ["Frame rate",    fps == null
                                    ? "source — reading it off your first clip…"
                                    : `${fps} fps${fpsFromSource ? " (from your first clip)" : ""}`],
                // The name the render will carry. Both settings above feed
                // the tag, so seeing the filename is the quickest check that
                // this run will not overwrite the last one -- worth knowing
                // BEFORE committing two hours to it.
                ["Video file",    project.output.video === false
                                    ? "not this run"
                                    : (videoName || "naming it once the frame rate is known…")],
                ["Loudness",      project.output.normalizeAudio ? "−16 LUFS" : "off"],
                ["Funscripts",    cov.detected
                                    ? `${cov.detected} channel${cov.detected === 1 ? "" : "s"} · `
                                      + cov.groups.filter(g => g.included).map(g => g.label).join(" · ")
                                    : "none detected"],
              ].map(([k, v]) => (
                <tr key={k}>
                  <td style={{ padding: "6px 0", color: "var(--text-muted)", width: 140 }}>{k}</td>
                  <td className="mono" style={{ padding: "6px 0", color: "var(--text)" }}>{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        <Card>
          <FASectionLabel>Outputs that will be written</FASectionLabel>
          <div style={{ marginBottom: 8, fontSize: 11, color: "var(--text-dim)", lineHeight: 1.5 }}>
            into{" "}
            <span className="mono" style={{ color: "var(--text-muted)", wordBreak: "break-all" }}>
              {project.output.folder || "the folder you chose in Save As"}
            </span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {[
              // The rendered size goes in the name (`.1080p30.mp4`) so a 4k
              // render lands beside the 1080p one instead of over it. With
              // either setting on `source` the value is probed at forge time,
              // so the tag genuinely is not known yet -- say that rather than
              // print a name that turns out to be wrong.
              { f: videoName || `${project.name}.<size>.mp4`,
                on: project.output.video },
              // One row per channel the engine will actually forge, named
              // the way it names them: main is the bare .funscript, every
              // other channel takes its own suffix. This list used to be
              // hardcoded — it advertised a .alt.funscript and a
              // .stereostim.wav that nothing produces, and never mentioned
              // the device channels that do get written.
              ...cov.groups.filter(g => g.included).flatMap(g => g.channels.map(c => ({
                // The path the ENGINE writes, not the channel key. The key is
                // station-qualified (`tcode:main`) and a colon cannot be in a
                // Windows filename -- this panel was advertising files that
                // could never exist.
                f: funscriptRelPath(c.id, project.name),
                on: project.output.funscripts !== false,
                sub: c.id !== "main",
              }))),
              { f: projectFileName(project.name), on: true },
            ].filter(x => x.on).map((x, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 8,
                                      padding: "5px 8px", paddingLeft: x.sub ? 22 : 8,
                                      background: "var(--surface-2)", borderRadius: 4 }}>
                <Icon name="file-text" size={12} style={{ color: "var(--text-dim)" }} />
                <span className="mono" style={{ fontSize: 11.5, color: "var(--text)" }}>{x.f}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <div style={{ marginTop: 18 }}>
        <ChapterMarkersCard project={project} videoName={videoName} />
      </div>

      <div style={{ marginTop: 18 }}>
        <ForgePanel project={project} onForge={onForge} onCancelForge={onCancelForge}
                    cancelling={cancelling} forging={forging} progress={progress}
                    forgeStage={forgeStage} totalMs={totalMs} />
      </div>
    </FATabBody>
  );
}

// ── Chapter markers card ──────────────────────────────────────────
// Every section becomes a chapter in the output MP4 (and a chapter
// marker in the output funscript). This card shows the list explicitly
// so the user can see what's written before they forge.
function ChapterMarkersCard({ project, videoName }) {
  // Compute each section's start time (sum of preceding section
  // durations + their leading joiner totals).
  let cursor = 0;
  const rows = project.sections.map((sec, i) => {
    const start = cursor;
    const dur = sec.segments.reduce((a, s) => a + effectiveDurMs(s), 0);
    cursor += dur;
    // Only the joiner's hold advances the timeline; see FA_DATA.joinerAddedMs.
    // This card is where a user checks where the chapters will land, so it
    // was the worst place to be 2s per boundary out.
    const nextJoiner = project.sections[i + 1]?.joiner;
    if (nextJoiner) cursor += FA_DATA.joinerAddedMs(nextJoiner);
    return { sec, idx: i, start, dur };
  });

  return (
    <Card padding={16}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 12, marginBottom: 12 }}>
        <Icon name="bookmark" size={16} style={{ color: "var(--accent-warm)", marginTop: 1 }} />
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13.5, fontWeight: 600 }}>Chapter markers</div>
          <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 3, lineHeight: 1.5 }}>
            Every section becomes one chapter — in the output MP4 (playable in any modern player)
            and in the output funscript (read by FunscriptForge and haptic players that respect
            chapter metadata). Both get the same list. Each <span className="mono">.forge</span> scene
            you import lands in its own section, so it's its own chapter; the section name is the
            chapter title, and you can rename it on the Build tab.
          </div>
        </div>
        <Pill tone="accent" style={{ fontSize: 10 }}>{rows.length} chapter{rows.length === 1 ? "" : "s"}</Pill>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {rows.map(({ sec, idx, start, dur }) => (
          <div key={sec.id} style={{
            display: "flex", alignItems: "center", gap: 12,
            padding: "8px 12px",
            background: "var(--surface-2)", border: "1px solid var(--border)",
            borderRadius: 6,
          }}>
            <span style={{ width: 4, alignSelf: "stretch", borderRadius: 2,
                            background: sec.color, opacity: 0.7 }} />
            <span className="mono" style={{ fontSize: 11, fontWeight: 700,
                                              color: "var(--accent-warm)", width: 50 }}>
              ch.{String(idx + 1).padStart(2, "0")}
            </span>
            <span className="mono" style={{ fontSize: 12, color: "var(--text)", width: 70 }}>
              {fmtTotal(start)}
            </span>
            <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text)", flex: 1,
                            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {sec.title}
            </span>
            <span className="mono" style={{ fontSize: 11, color: "var(--text-dim)" }}>
              {fmtTotal(dur)}
            </span>
            <span className="mono" style={{ fontSize: 10.5, color: "var(--text-dim)",
                                              minWidth: 70, textAlign: "right" }}>
              {sec.segments.length} clip{sec.segments.length === 1 ? "" : "s"}
            </span>
          </div>
        ))}
      </div>

      <div className="mono" style={{
        marginTop: 12, fontSize: 10.5, color: "var(--text-dim)",
      }}>
        written to <span style={{ color: "var(--text-muted)" }}>
          {videoName || renderedVideoName(project) || `${project.name}.<size>.mp4`}</span>
        {" "}as MOV/MP4 chapter atoms · also embedded in
        <span style={{ color: "var(--text-muted)" }}> {project.name}.funscript</span> metadata
      </div>
    </Card>
  );
}

// How long the forge will take, from the encoder this machine will
// ACTUALLY use. The old line was `totalMs / 30000` — a fixed ~0.5x
// realtime guess that ignored both the encoder and the resolution it
// claimed to account for, so a GPU box was quoted 27 minutes for a job
// that took two.
// The frame rate the forge will ACTUALLY use.
//
// `source` is a legitimate setting -- match the first clip -- but it is not
// an answer to "what am I about to render". Worse, it left the summary
// naming a file that would never exist: `renderTag` needs a number, so a
// project on `source` fell back to `<name>.mp4` while the forge wrote
// `<name>.1080p25.mp4`. The engine resolves this by probing the first real
// video segment at forge time; this does the same, up front.
//
// Returns { fps, source } -- `source` true when it came from a probe.
function useEffectiveFps(project) {
  const set = Number.parseInt(project.output?.frameRate, 10);
  const explicit = Number.isFinite(set) ? set : null;
  // The same segment the engine picks: the first that is not a still.
  const firstVideo = project.sections
    ?.flatMap((s) => s.segments)
    ?.find((s) => s.file && s.kind !== 'still')?.file || null;

  const [probed, setProbed] = useState(null);
  useEffect(() => {
    if (explicit !== null || !firstVideo) { setProbed(null); return undefined; }
    let cancelled = false;
    probeMedia(firstVideo)
      .then((r) => {
        if (cancelled || !r || r.fps == null) return;
        setProbed(Math.round(r.fps));
      })
      .catch(() => { /* leave it unresolved rather than guess */ });
    return () => { cancelled = true; };
  }, [explicit, firstVideo]);

  if (explicit !== null) return { fps: explicit, source: false };
  return { fps: probed, source: true };
}

function useForgeEstimate(project, totalMs) {
  const [enc, setEnc] = useState(null);
  useEffect(() => {
    let cancelled = false;
    videoEncoder()
      .then((e) => { if (!cancelled) setEnc(e); })
      .catch(() => { /* fall back to the unqualified estimate */ });
    return () => { cancelled = true; };
  }, []);

  if (!totalMs) return "Add clips on the Build tab to see an estimate.";
  if (project.output?.video === false) {
    return "Video is off — funscripts and haptic audio only, which take seconds.";
  }
  if (!enc) return "Estimating forge time…";

  const cost = enc.resolution_cost?.[project.output?.resolution] ?? 1;
  const seconds = (totalMs / 1000) / ((enc.rate_1080p || 0.8) / cost);
  const pretty = seconds < 90
    ? `about ${Math.max(10, Math.round(seconds / 10) * 10)} seconds`
    : `about ${Math.max(2, Math.round(seconds / 60))} minutes`;
  return `Roughly ${pretty} on ${enc.label}.`;
}

function ForgePanel({ project, onForge, onCancelForge, cancelling,
                      forging, progress, forgeStage, totalMs }) {
  const estimate = useForgeEstimate(project, totalMs);
  return (
    <Card padding={20} style={{
      background: "linear-gradient(135deg, #1a0e1e 0%, #1a1d27 60%, #0e1117 100%)",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <div style={{
          width: 56, height: 56, borderRadius: 10,
          background: "rgba(255,75,75,0.1)",
          border: "1px solid rgba(255,75,75,0.3)",
          display: "grid", placeItems: "center",
          flexShrink: 0,
        }}>
          <Icon name="hammer" size={26} style={{ color: "var(--accent)" }} />
        </div>
        <div style={{ flex: 1 }}>
          <h3 style={{ fontSize: 18, fontWeight: 700, margin: 0 }}>
            {forging ? "Forging…" : "Ready to forge"}
          </h3>
          <p style={{ fontSize: 12.5, color: "var(--text-muted)", margin: "4px 0 0", lineHeight: 1.5 }}>
            {forging
              ? "Running ffmpeg passes. Don't close the app — output appears in your project folder as each step completes."
              : <>About <span className="mono" style={{ color: "var(--text)" }}>{fmtTotal(totalMs)}</span> of
                  output{project.output.video === false ? "" : ` at ${project.output.resolution}`}. {estimate}</>}
          </p>
        </div>
        {/* Cancel sits beside "Forging…", which is where someone looks when
            they have changed their mind. It says what it costs, because the
            reassuring half is not obvious: the encode goes to a temp file,
            so stopping loses only this run, never the render already in the
            output folder. */}
        {forging && (
          <Button kind="ghost" size="md" icon="x" onClick={onCancelForge}
                  disabled={cancelling}
                  title="Stops this render. Any earlier render in the output folder is left untouched.">
            {cancelling ? "Cancelling…" : "Cancel"}
          </Button>
        )}
        <Button kind="primary" size="md" icon="hammer" onClick={onForge} disabled={forging}>
          {forging ? "Forging…" : "Forge"}
        </Button>
      </div>

      {forging && progress != null && (
        <div style={{ marginTop: 18 }}>
          <div style={{ height: 8, background: "rgba(255,255,255,0.06)",
                          borderRadius: 4, overflow: "hidden" }}>
            <span style={{
              display: "block", width: `${Math.round(progress * 100)}%`, height: "100%",
              background: "linear-gradient(90deg, var(--accent-warm), var(--accent))",
              transition: "width 0.3s ease",
            }} />
          </div>
          <div className="mono" style={{ marginTop: 8, fontSize: 11, color: "var(--text-muted)",
                                          display: "flex", justifyContent: "space-between" }}>
            <span>{forgeStage || "Working…"}</span>
            <span>{Math.round(progress * 100)}%</span>
          </div>
        </div>
      )}
    </Card>
  );
}

// ── Overlays over the whole compilation ──────────────────────────
// A logo that appears for a while, a credits roll over the closing
// bumper. Timed in absolute seconds from the start of the output, which
// is what lets them reach the branding at either end -- a Section's own
// overlays are timed from that section and cannot leave it.

// The nine both `_POSITION_EXPRS` and `_TEXT_POSITION_EXPRS` share, so a
// position stays valid if an overlay is switched between image and text.
// The filters accept longhand spellings too ("bottom-center"); the short
// ones are what we write.
// `value`, not `v`: Segmented reads `opt.value`. Spelling it `v` gave every
// option an undefined key, fired onChange with undefined, and left nothing
// ever highlighted -- the React key warning was the visible end of a picker
// that did not work at all.
const OVERLAY_POSITIONS = [
  { value: "tl", label: "Top left" },
  { value: "tc", label: "Top" },
  { value: "tr", label: "Top right" },
  { value: "ml", label: "Left" },
  { value: "center", label: "Centre" },
  { value: "mr", label: "Right" },
  { value: "bl", label: "Bottom left" },
  { value: "bc", label: "Bottom" },
  { value: "br", label: "Bottom right" },
];

const fmtSecs = (s) => {
  const n = Math.max(0, Math.round(Number(s) || 0));
  return `${String(Math.floor(n / 60)).padStart(2, "0")}:${String(n % 60).padStart(2, "0")}`;
};

// `duration_s === 0` means "run to the end" in the engine, so the UI has
// to say that rather than print a stop time of 00:00.
function overlayWindowLabel(ov) {
  const start = fmtSecs(ov.start_s);
  if (!ov.duration_s || Number(ov.duration_s) <= 0) return `${start} → end`;
  return `${start} → ${fmtSecs(Number(ov.start_s || 0) + Number(ov.duration_s))}`;
}

function OverlaysCard({ overlays = [], onAdd, onEdit, onRemove }) {
  return (
    <Card>
      <FASectionLabel>Overlays</FASectionLabel>
      <div style={{ marginBottom: 10, fontSize: 11, color: "var(--text-dim)", lineHeight: 1.5 }}>
        A logo or a line of text laid over the finished compilation, timed in
        seconds from the very start. These are the only overlays that reach
        the branding at either end, so closing credits go here.
      </div>

      {overlays.length === 0 ? (
        <div style={{
          border: "1px dashed var(--border)", borderRadius: 8,
          padding: "12px 14px", fontSize: 11.5, color: "var(--text-dim)",
        }}>
          None. The compilation plays as-is.
        </div>
      ) : overlays.map((ov, i) => (
        <div key={ov.id || i} style={{
          display: "flex", alignItems: "center", gap: 10, marginBottom: 6,
          border: "1px solid var(--border)", borderRadius: 8, padding: "8px 10px",
        }}>
          <Icon name={ov.kind === "text" ? "type" : "image"} size={14}
                style={{ color: "var(--text-muted)", flexShrink: 0 }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 12, fontWeight: 600, overflow: "hidden",
                           textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {ov.kind === "text"
                ? (ov.text || "").split("\n")[0] || "(empty text)"
                : fileNameOf(ov.file) || "(no file)"}
            </div>
            <div className="mono" style={{ fontSize: 10.5, color: "var(--text-dim)" }}>
              {ov.anchor === "outro" ? "outro " : ""}{overlayWindowLabel(ov)} · {
                (OVERLAY_POSITIONS.find(p => p.value === ov.position) || {}).label || ov.position
              }
            </div>
          </div>
          <Button kind="ghost" size="sm" onClick={() => onEdit?.(i)}>Edit</Button>
          <Button kind="ghost" size="icon" title="Remove this overlay"
                  onClick={() => onRemove?.(i)}><Icon name="x" size={13} /></Button>
        </div>
      ))}

      <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
        <Button kind="secondary" size="sm" icon="image"
                onClick={() => onAdd?.("image")}>Add image&#8230;</Button>
        <Button kind="secondary" size="sm" icon="type"
                onClick={() => onAdd?.("text")}>Add text&#8230;</Button>
      </div>
    </Card>
  );
}

// The editor. Edits a COPY and only calls back on Save, so Cancel really
// does discard -- editing the project in place would leave a half-typed
// start time behind after a cancel.
function OverlayDialog({ overlay, hasOutro, onSave, onClose }) {
  const [d, setD] = useState(() => ({ ...overlay }));
  const set = (patch) => setD((prev) => ({ ...prev, ...patch }));
  const isText = d.kind === "text";
  const anchored = d.anchor === "outro" && hasOutro;

  // Stop time, not duration. The engine stores a duration, but "when does
  // it go away" is the question someone actually has in mind, and making
  // them subtract is how off-by-a-second mistakes happen.
  const startS = Number(d.start_s) || 0;

  // Both boxes keep their own TEXT while you type, and only convert to the
  // model on blur.
  //
  // Deriving the stop box from `duration_s` on every keystroke made it
  // impossible to fill in. With a start of 5, typing "10" begins with "1":
  // that computed a duration of max(0, 1 - 5) = 0, which means "run to the
  // end", which re-rendered the box as empty -- so the second keystroke had
  // nothing to follow and the field could never hold a number larger than
  // one digit. Reported as "would not let me put in the stop time".
  //
  // The same trap applies to start: clearing it to retype would snap to 0.
  const [startText, setStartText] = useState(() => String(Number(overlay.start_s) || 0));
  const [stopText, setStopText] = useState(() => {
    const dur = Number(overlay.duration_s) || 0;
    return dur > 0 ? String((Number(overlay.start_s) || 0) + dur) : "";
  });

  const commitStart = () => {
    const v = Number(startText);
    const next = Number.isFinite(v) && v > 0 ? v : 0;
    setStartText(String(next));
    // A stop already typed keeps its meaning: it is an absolute time, so
    // moving the start changes the duration, not where it ends.
    const stop = Number(stopText);
    const patch = { start_s: next };
    if (stopText.trim() !== "" && Number.isFinite(stop)) {
      patch.duration_s = Math.max(0, stop - next);
    }
    set(patch);
  };

  const commitStop = () => {
    if (stopText.trim() === "") { set({ duration_s: 0 }); return; }
    const v = Number(stopText);
    if (!Number.isFinite(v)) { setStopText(""); set({ duration_s: 0 }); return; }
    // A stop at or before the start would render nothing at all. Say so by
    // snapping it back rather than silently keeping an empty window.
    if (v <= startS) { setStopText(""); set({ duration_s: 0 }); return; }
    set({ duration_s: v - startS });
  };

  async function pickImage() {
    const f = await pickFile({
      title: "Select an overlay image",
      filterName: "Image", extensions: ["png", "jpg", "jpeg", "webp"],
    });
    if (f) set({ file: f });
  }

  const canSave = isText ? !!(d.text || "").trim() : !!d.file;

  return (
    <Modal title={isText ? "Text overlay" : "Image overlay"}
           icon={isText ? "type" : "image"} width={520} onClose={onClose}
           subtitle="Timed in seconds from the start of the whole compilation, branding included.">
      {isText ? (
        <Field label="Text" hint="One line per line. Blank lines are kept.">
          <textarea value={d.text || ""} onChange={(e) => set({ text: e.target.value })}
                    rows={4} spellCheck={false}
                    style={{ width: "100%", resize: "vertical", padding: "8px 10px",
                             background: "var(--surface-2, var(--surface))",
                             color: "var(--text)", fontFamily: "inherit", fontSize: 12.5,
                             border: "1px solid var(--border)", borderRadius: 8 }} />
        </Field>
      ) : (
        <Field label="Image" hint="PNG with transparency keeps its alpha.">
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div className="mono" style={{
              flex: 1, minWidth: 0, fontSize: 11.5, color: "var(--text-muted)",
              overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
            }}>{d.file || "no file chosen"}</div>
            <Button kind="secondary" size="sm" onClick={pickImage}>Choose&#8230;</Button>
          </div>
        </Field>
      )}

      {/* Credits are placed relative to the bumper they sit on, and their
          absolute time cannot be known: the total duration is only settled
          at forge time once every clip has been probed. */}
      {hasOutro && (
        <Field label="Timed from"
               hint={anchored
                 ? "0 is the first frame of the closing branding."
                 : "0 is the first frame of the whole compilation."}>
          <Segmented value={d.anchor === "outro" ? "outro" : "start"}
                     onChange={(v) => set({ anchor: v })}
                     options={[
                       { value: "start", label: "Start of compilation" },
                       { value: "outro", label: "Closing branding" },
                     ]} />
        </Field>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <Field label={anchored ? "Start (seconds into the bumper)" : "Start (seconds)"}>
          <TextInput mono value={startText} onChange={setStartText}
                     onBlur={commitStart} />
        </Field>
        <Field label="Stop (seconds)" hint="blank = run to the end">
          <TextInput mono value={stopText} onChange={setStopText}
                     placeholder="end" onBlur={commitStop} />
        </Field>
      </div>

      {/* Multi-line text takes its left/centre/right alignment FROM the
          position -- bl aligns left, bc centre, br right. That is the
          engine's rule, not a separate control, and worth saying so rather
          than leaving someone hunting for an alignment picker. */}
      <Field label="Position"
             hint={isText ? "Also sets how multiple lines align to each other." : null}>
        <Segmented options={OVERLAY_POSITIONS}
                   value={d.position || "center"}
                   onChange={(v) => set({ position: v })} />
      </Field>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <Field label="Fade in (seconds)">
          <TextInput mono value={String(Number(d.fade_in_s) || 0)}
                     onChange={(v) => set({ fade_in_s: Math.max(0, Number(v) || 0) })} />
        </Field>
        <Field label="Fade out (seconds)">
          <TextInput mono value={String(Number(d.fade_out_s) || 0)}
                     onChange={(v) => set({ fade_out_s: Math.max(0, Number(v) || 0) })} />
        </Field>
      </div>

      {isText ? (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <Field label="Colour">
            <TextInput mono value={d.text_color || "#ffffff"}
                       onChange={(v) => set({ text_color: v })} />
          </Field>
          <Field label="Size">
            <TextInput mono value={String(Number(d.font_size) || 48)}
                       onChange={(v) => set({ font_size: Math.max(1, Number(v) || 48) })} />
          </Field>
        </div>
      ) : (
        <Field label="Scale (%)" hint="100 is the image's own size.">
          <TextInput mono value={String(Number(d.scale_pct) || 100)}
                     onChange={(v) => set({ scale_pct: Math.max(1, Number(v) || 100) })} />
        </Field>
      )}

      <ModalFooter>
        <Button kind="ghost" size="sm" onClick={onClose}>Cancel</Button>
        <Button kind="primary" size="sm" disabled={!canSave}
                onClick={() => onSave?.(d)}>Save</Button>
      </ModalFooter>
    </Modal>
  );
}

// One branding slot. Empty is the resting state and looks like it: a
// dashed placeholder, not a control someone already set.
function BrandingSlot({ which, label, seg, onPick, onClear }) {
  const name = seg ? (seg.title || fileNameOf(seg.file)) : null;
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>{label}</div>
      {seg ? (
        <div style={{ display: "flex", alignItems: "center", gap: 8,
                      padding: "7px 10px", borderRadius: 6,
                      background: "var(--surface-2)", border: "1px solid var(--border)" }}>
          <Icon name="clapperboard" size={13} style={{ color: "var(--accent-warm)", flexShrink: 0 }} />
          <span style={{ flex: 1, minWidth: 0, fontSize: 12, overflow: "hidden",
                         textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                title={seg.file}>{name}</span>
          <Button kind="ghost" size="sm" onClick={() => onPick?.(which)}>Change</Button>
          <Button kind="ghost" size="icon" title="Use no branding here"
                  onClick={() => onClear?.(which)}><Icon name="x" size={12} /></Button>
        </div>
      ) : (
        <Button kind="secondary" size="sm" icon="plus"
                onClick={() => onPick?.(which)}>Choose a .forge scene…</Button>
      )}
    </div>
  );
}

function fileNameOf(p) {
  const s = String(p || "");
  const cut = Math.max(s.lastIndexOf("/"), s.lastIndexOf("\\"));
  const base = cut < 0 ? s : s.slice(cut + 1);
  return base.replace(/\.[^.]+$/, "") || "scene";
}

// ── Small toggle (used by Project / Channels) ─────────────────────
function Toggle({ label, checked, disabled, onChange }) {
  return (
    <button disabled={disabled} onClick={() => !disabled && onChange?.(!checked)} style={{
      display: "flex", alignItems: "center", gap: 10, width: "100%",
      padding: "6px 0", background: "transparent", border: "none",
      cursor: disabled ? "not-allowed" : "pointer", textAlign: "left",
      color: "var(--text)", fontFamily: "inherit", fontSize: 12.5,
    }}>
      <span style={{
        width: 30, height: 18, borderRadius: 10, position: "relative", flexShrink: 0,
        background: checked ? "var(--accent)" : "var(--surface-2)",
        border: `1px solid ${checked ? "var(--accent)" : "var(--border)"}`,
        transition: "background 120ms, border-color 120ms",
      }}>
        <span style={{
          position: "absolute", top: 1, left: checked ? 13 : 1, width: 14, height: 14,
          background: "#fff", borderRadius: "50%",
          transition: "left 120ms var(--ease-standard)",
        }} />
      </span>
      <span>{label}</span>
    </button>
  );
}

Object.assign(window, { OutputTab, ForgeTab, Toggle });


export { BrandingSlot, ChapterMarkersCard, ForgePanel, ForgeTab, OverlayDialog, OverlaysCard, OutputChannelsCard,
         OutputTab, ResolutionPicker, Toggle };
