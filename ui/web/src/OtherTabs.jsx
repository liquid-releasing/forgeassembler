/* @esm-converted */
import React from 'react';
const { useState, useEffect } = React;
import { FASectionLabel, FATabBody, FATabHeader, fmtTotal } from './AppShell';
import { ParamControl, TimingVisual } from './JoinerEditor';
import { Section } from './TitleEditor';
import { FA_DATA } from './data';
import { Button, Card, Field, Icon, Pill, Segmented, Slider, TextInput } from './primitives';
import { segmentHasChannel } from './lib/projectAdapter';

// Sketched other pipeline tabs. Intentionally light — the Build tab is
// where the design work is concentrated; these convey the structure
// and the chain pattern.

// ── Project tab removed ───────────────────────────────────────────
// Was a dead form (basename/output-folder now set via Save As; recent
// projects + New/Open moved to the Home screen — see HomeScreen.jsx).
// The two real "Produce" toggles folded into the Output tab below.

// ── Channels tab removed — folded into Output. Detection-driven now.

// ── Output tab (also absorbs channel coverage) ───────────────────
// Channels aren't opt-in. Detection scans the clip folders; the user's
// real decision is: when a clip is MISSING this channel, do we
// (a) generate a basic fallback so the channel is continuous, or
// (b) leave that section blank (silence / no actions)?
function OutputTab({ project, channelGapPolicy, onSetChannelGapPolicy,
                    onSetOutput, onSetChannels }) {
  const out = project.output || {};
  const chans = project.channels || {};
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
          </div>
          <div style={{ marginTop: 10, padding: "8px 10px", background: "var(--surface-2)",
                         border: "1px solid var(--border)", borderRadius: 6,
                         fontSize: 11, color: "var(--text-muted)" }}>
            Chapter markers are always written when video is produced.
          </div>
        </Card>
        <Card>
          <FASectionLabel>Resolution</FASectionLabel>
          <ResolutionPicker value={project.output.resolution} />
        </Card>
        <Card>
          <FASectionLabel>Quality &amp; frame rate</FASectionLabel>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <Field label="Quality">
              <Segmented value="medium" onChange={() => {}}
                          options={[
                            { value: "low", label: "Low · CRF 28" },
                            { value: "medium", label: "Medium · CRF 23" },
                            { value: "high", label: "High · CRF 18" },
                          ]} />
            </Field>
            <Field label="Frame rate">
              <Segmented value="source" onChange={() => {}}
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
              Audio beds (set on Build) ride over per-clip audio across joiners.
            </div>
          </div>
        </Card>
        <Card>
          <FASectionLabel right={<Button kind="ghost" size="sm" icon="plus">Add bug</Button>}>
            Bug overlay
          </FASectionLabel>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <Field label="PNG file"><TextInput value="" placeholder="None — click Add bug to pick a PNG" mono /></Field>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              <Field label="Corner">
                <Segmented value="br" onChange={() => {}}
                            options={[{ value: "tl", label: "TL" }, { value: "tr", label: "TR" },
                                      { value: "bl", label: "BL" }, { value: "br", label: "BR" }]} />
              </Field>
              <Field label="Margin"><TextInput value="32 px" mono /></Field>
            </div>
            <Slider value={80} min={0} max={100} label="Opacity" valueLabel="80%" onChange={() => {}} />
          </div>
        </Card>
      </div>

      <div style={{ marginTop: 20 }}>
        <OutputChannelsCard project={project}
                              channelGapPolicy={channelGapPolicy}
                              onSetChannelGapPolicy={onSetChannelGapPolicy} />
      </div>
    </FATabBody>
  );
}

// ── Output channels card (was its own tab) ───────────────────────
// Detected channels appear automatically; the user decides per
// partially-covered channel how to fill the gaps.
function OutputChannelsCard({ project, channelGapPolicy, onSetChannelGapPolicy }) {
  const flat = project.sections.flatMap(s => s.segments);
  const segCount = flat.length;

  // Build per-channel coverage from per-clip detection
  const all = FA_DATA.CHANNELS.filter(c => !c.future);
  const channels = all.map(c => {
    // For "still" segments we don't expect a funscript — those are
    // exempt rather than counted as "missing".
    const eligible = flat.filter(s => s.kind !== "still" || c.id === "audio_estim");
    const have = eligible.filter(s => segmentHasChannel(s, c.id));
    return {
      ...c,
      detected: have.length > 0,
      have: have.length,
      eligible: eligible.length,
      pct: eligible.length ? (have.length / eligible.length) * 100 : 0,
    };
  });

  const detected = channels.filter(c => c.detected);
  const notDetected = channels.filter(c => !c.detected);

  return (
    <Card padding={18}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 14, marginBottom: 14 }}>
        <Icon name="layers" size={18} style={{ color: "var(--accent-warm)", marginTop: 1 }} />
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>Output channels</div>
          <div style={{ fontSize: 12, color: "var(--text-muted)", lineHeight: 1.5, maxWidth: 720 }}>
            Every funscript channel ForgeAssembler detected in your clips is included in the output. When a channel
            is only on some clips, you decide what happens at the gaps: synthesise a basic fallback so the channel
            is continuous, or leave those sections blank.
          </div>
        </div>
        <Pill tone="accent" style={{ fontSize: 10 }}>{detected.length} detected</Pill>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {detected.map(c => {
          const full = c.have === c.eligible;
          const policy = channelGapPolicy[c.id] || "blank";
          return (
            <div key={c.id} style={{
              display: "grid", gridTemplateColumns: "180px 1fr 220px",
              alignItems: "center", gap: 14,
              padding: "10px 12px",
              background: "var(--surface-2)", border: "1px solid var(--border)",
              borderRadius: 8,
            }}>
              <div>
                <div style={{ fontSize: 12.5, fontWeight: 600 }}>{c.label}</div>
                <div className="mono" style={{ fontSize: 10.5, color: "var(--text-dim)", marginTop: 1 }}>{c.desc}</div>
              </div>

              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                  <div style={{ flex: 1, height: 6, background: "var(--bg)",
                                  borderRadius: 3, overflow: "hidden" }}>
                    <span style={{
                      display: "block", width: `${c.pct}%`, height: "100%",
                      background: full ? "var(--success)" : "var(--warn)",
                    }} />
                  </div>
                  <span className="mono" style={{ fontSize: 11, color: full ? "var(--success)" : "var(--warn)",
                                                    fontWeight: 600, width: 84, textAlign: "right" }}>
                    {c.have} / {c.eligible} clips
                  </span>
                </div>
                <div style={{ fontSize: 11, color: "var(--text-dim)" }}>
                  {full
                    ? "Full coverage — no gaps to resolve."
                    : `Missing on ${c.eligible - c.have} clip${(c.eligible - c.have) === 1 ? "" : "s"}.`}
                </div>
              </div>

              {full ? (
                <div style={{ display: "flex", alignItems: "center", gap: 6,
                                color: "var(--success)", fontSize: 11.5, fontWeight: 600,
                                justifyContent: "flex-end" }}>
                  <Icon name="circle-check-big" size={13} />
                  Continuous
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 4, alignItems: "flex-end" }}>
                  <span className="mono" style={{ fontSize: 10, color: "var(--text-dim)",
                                                    textTransform: "uppercase", letterSpacing: "0.06em",
                                                    fontWeight: 700 }}>
                    Fill gaps with
                  </span>
                  <Segmented value={policy} onChange={(v) => onSetChannelGapPolicy(c.id, v)}
                              options={[
                                { value: "blank",    label: c.id === "audio_estim" ? "Silence" : "Blank" },
                                { value: "generate", label: c.id === "audio_estim" ? "Tone" : "Basic" },
                              ]} />
                  <span style={{ fontSize: 10.5, color: "var(--text-dim)", textAlign: "right",
                                  maxWidth: 220, lineHeight: 1.45 }}>
                    {policy === "blank"
                      ? (c.id === "audio_estim"
                          ? "Insert silence for missing sections (lockstep with video)."
                          : "Hold the last position — no new actions during the gap.")
                      : (c.id === "audio_estim"
                          ? "Generate a low-level guide tone derived from the main channel."
                          : "Synthesise basic motion from the main channel as a fallback.")}
                  </span>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {notDetected.length > 0 && (
        <details style={{ marginTop: 12 }}>
          <summary style={{ cursor: "pointer", fontSize: 11.5, color: "var(--text-dim)",
                              padding: "6px 10px", borderRadius: 6,
                              background: "var(--surface-2)", border: "1px solid var(--border)",
                              listStyle: "none", userSelect: "none" }}>
            <span style={{ fontWeight: 600 }}>{notDetected.length} channel{notDetected.length === 1 ? "" : "s"} not detected</span>
            <span style={{ marginLeft: 8 }}>· {notDetected.map(c => c.label).join(" · ")}</span>
          </summary>
          <div style={{ marginTop: 6, padding: "8px 12px", fontSize: 11.5, color: "var(--text-muted)",
                          lineHeight: 1.5 }}>
            These weren't found alongside any clip in this project, so they aren't in the output.
            Add a clip that carries one of them to the Build tab and it'll appear here.
          </div>
        </details>
      )}
    </Card>
  );
}

function ResolutionPicker({ value }) {
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
                <button key={o.v} style={{
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
function ForgeTab({ project, totalMs, onForge, forging, progress, forgeStage, channelGapPolicy }) {
  // Detect channels present anywhere in the project (detection-driven output).
  const flat = project.sections.flatMap(s => s.segments);
  const detected = FA_DATA.CHANNELS.filter(c => !c.future)
    .filter(c => flat.some(s => s.channels.includes(c.id)));
  const has = (id) => detected.some(c => c.id === id);

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
                ["Sections",      project.sections.length],
                ["Segments",      flat.length],
                ["Audio beds",    project.audioBeds.length],
                ["Total duration", fmtTotal(totalMs)],
                ["Resolution",    project.output.resolution],
                ["Loudness",      project.output.normalizeAudio ? "−16 LUFS" : "off"],
                ["Channels",      detected.length ? detected.map(c => c.label).join(" · ") : "none detected"],
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
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {[
              { f: `${project.name}.mp4`,                       on: project.output.video },
              { f: `${project.name}.funscript`,                 on: has("main") },
              { f: `${project.name}.pitch.funscript`,           on: has("multi_axis"), sub: true },
              { f: `${project.name}.roll.funscript`,            on: has("multi_axis"), sub: true },
              { f: `${project.name}.alpha.funscript`,           on: has("estim_3p"),   sub: true },
              { f: `${project.name}.beta.funscript`,            on: has("estim_3p"),   sub: true },
              { f: `${project.name}.alt.funscript`,             on: has("alt"),        sub: true },
              { f: `${project.name}.stereostim.wav`,            on: has("audio_estim") },
              { f: `${project.name}.forgeproject.json`,         on: true },
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
        <ChapterMarkersCard project={project} />
      </div>

      <div style={{ marginTop: 18 }}>
        <ForgePanel project={project} onForge={onForge} forging={forging} progress={progress} forgeStage={forgeStage} totalMs={totalMs} />
      </div>
    </FATabBody>
  );
}

// ── Chapter markers card ──────────────────────────────────────────
// Every section becomes a chapter in the output MP4 (and a chapter
// marker in the output funscript). This card shows the list explicitly
// so the user can see what's written before they forge.
function ChapterMarkersCard({ project }) {
  // Compute each section's start time (sum of preceding section
  // durations + their leading joiner totals).
  let cursor = 0;
  const rows = project.sections.map((sec, i) => {
    const start = cursor;
    const dur = sec.segments.reduce((a, s) => a + s.durMs, 0);
    cursor += dur;
    if (i < project.sections.length - 1) {
      const nextJoiner = project.sections[i + 1].joiner;
      if (nextJoiner && nextJoiner.kind !== "none") {
        cursor += FA_DATA.joinerTotalMs(nextJoiner);
      }
    }
    return { sec, idx: i, start, dur };
  });

  return (
    <Card padding={16}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 12, marginBottom: 12 }}>
        <Icon name="bookmark" size={16} style={{ color: "var(--accent-warm)", marginTop: 1 }} />
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13.5, fontWeight: 600 }}>Chapter markers</div>
          <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 3, lineHeight: 1.5 }}>
            Every section becomes a chapter in the output MP4 (playable in any modern player) and a
            chapter marker in the output funscript (consumed by FunscriptForge and haptic players
            that respect chapter metadata). Section names go into the chapter title —
            rename them on the Build tab.
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
        written to <span style={{ color: "var(--text-muted)" }}>{project.name}.mp4</span>
        {" "}as MOV/MP4 chapter atoms · also embedded in
        <span style={{ color: "var(--text-muted)" }}> {project.name}.funscript</span> metadata
      </div>
    </Card>
  );
}

function ForgePanel({ project, onForge, forging, progress, forgeStage, totalMs }) {
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
              : <>About <span className="mono" style={{ color: "var(--text)" }}>{fmtTotal(totalMs)}</span> of output. Estimated forge time at this resolution: <span className="mono" style={{ color: "var(--text)" }}>~{Math.max(1, Math.round(totalMs / 30000))} minutes</span>.</>}
          </p>
        </div>
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

// ── Joiners library (utility tab) ─────────────────────────────────
function JoinersTab({ project, onAddUserJoiner, onUpdateUserJoiner, onRemoveUserJoiner }) {
  const [authoring, setAuthoring] = React.useState(null);    // { id?, name, builtOn, params }
  const [previewKind, setPreviewKind] = React.useState(null); // for editing built-in defaults visually

  return (
    <FATabBody>
      <FATabHeader
        eyebrow="Library · Joiners"
        title="Joiners"
        subtitle={<>Joiners sit between sections and describe how one ends and the next begins. <strong style={{ color: "var(--text)" }}>Fade out → hold → fade in</strong> is one joiner — the same transition has three timing values you can tune. Author your own presets here and they show up in the inline picker on Build.</>}
        right={<Button kind="primary" size="sm" icon="plus"
                       onClick={() => setAuthoring({
                         name: "", builtOn: "fade_through_black",
                         params: FA_DATA.JOINER_KINDS.find(k => k.kind === "fade_through_black").defaults,
                       })}>New joiner</Button>}
      />

      <FASectionLabel>Built-in kinds</FASectionLabel>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 12, marginBottom: 24 }}>
        {FA_DATA.JOINER_KINDS.map(k => (
          <Card key={k.kind}>
            <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
              <div style={{ width: 36, height: 36, borderRadius: 8,
                              background: "var(--surface-2)", border: "1px solid var(--border)",
                              display: "grid", placeItems: "center", flexShrink: 0 }}>
                <Icon name={k.icon} size={16} />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 600 }}>{k.label}</div>
                <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4, lineHeight: 1.5 }}>{k.desc}</div>
                {k.params.length > 0 && (
                  <div style={{ marginTop: 10, display: "flex", flexWrap: "wrap", gap: 4 }}>
                    {k.params.map(p => (
                      <span key={p.id} className="mono" style={{
                        fontSize: 10.5, padding: "1px 7px", borderRadius: 3,
                        background: "var(--surface-2)", border: "1px solid var(--border)",
                        color: "var(--text-muted)",
                      }}>
                        {p.label}: <span style={{ color: "var(--text)" }}>
                          {p.kind === "color"
                            ? <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                                <span style={{ width: 9, height: 9, borderRadius: 2,
                                                background: k.defaults[p.id], border: "1px solid var(--border-strong)" }} />
                                {k.defaults[p.id]}
                              </span>
                            : `${k.defaults[p.id]}${p.unit || ""}`}
                        </span>
                      </span>
                    ))}
                  </div>
                )}
                {k.kind !== "none" && (
                  <Button kind="ghost" size="sm" icon="bookmark-plus"
                          style={{ marginTop: 10 }}
                          onClick={() => setAuthoring({
                            name: "", builtOn: k.kind, params: { ...k.defaults },
                          })}>
                    Create preset from this
                  </Button>
                )}
              </div>
            </div>
          </Card>
        ))}
      </div>

      <FASectionLabel right={<span className="mono" style={{ fontSize: 10.5, color: "var(--text-dim)" }}>
        {project.userJoiners?.length || 0} preset{(project.userJoiners?.length || 0) === 1 ? "" : "s"}
      </span>}>
        Your joiners
      </FASectionLabel>
      {(project.userJoiners?.length || 0) === 0 ? (
        <div style={{
          padding: 20, border: "1px dashed var(--border)", borderRadius: 8,
          color: "var(--text-muted)", fontSize: 12.5, textAlign: "center",
        }}>
          No custom joiners yet. Build on a kind above, or click <strong style={{ color: "var(--text)" }}>New joiner</strong> in the top-right.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {project.userJoiners.map(p => {
            const builtOn = FA_DATA.JOINER_KINDS.find(k => k.kind === p.builtOn);
            return (
              <Card key={p.id} padding={14}>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <div style={{ width: 30, height: 30, borderRadius: 6,
                                  background: "rgba(255,140,66,0.12)",
                                  border: "1px solid rgba(255,140,66,0.3)",
                                  display: "grid", placeItems: "center", flexShrink: 0 }}>
                    <Icon name={builtOn?.icon || "bookmark"} size={13}
                          style={{ color: "var(--accent-warm)" }} />
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 600 }}>{p.name}</div>
                    <div className="mono" style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>
                      {builtOn?.label.toLowerCase()} · {builtOn?.params
                        .filter(par => par.kind !== "color")
                        .map(par => `${par.label.toLowerCase()} ${p.params[par.id]}${par.unit || ""}`)
                        .join(" · ")}
                    </div>
                  </div>
                  <Button kind="ghost" size="sm" icon="pencil"
                          onClick={() => setAuthoring({ ...p })}>Edit</Button>
                  <Button kind="ghost" size="icon"
                          onClick={() => onRemoveUserJoiner(p.id)}><Icon name="trash-2" size={13} /></Button>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      {authoring && (
        <UserJoinerAuthor authoring={authoring}
                            onCancel={() => setAuthoring(null)}
                            onSave={(payload) => {
                              if (payload.id) onUpdateUserJoiner(payload);
                              else onAddUserJoiner(payload);
                              setAuthoring(null);
                            }} />
      )}
    </FATabBody>
  );
}

function UserJoinerAuthor({ authoring, onCancel, onSave }) {
  const [draft, setDraft] = React.useState(() => ({ ...authoring }));
  const kind = FA_DATA.JOINER_KINDS.find(k => k.kind === draft.builtOn);
  function setParam(id, v) { setDraft(d => ({ ...d, params: { ...d.params, [id]: v } })); }
  function setBuiltOn(newKind) {
    const k = FA_DATA.JOINER_KINDS.find(x => x.kind === newKind);
    setDraft(d => ({ ...d, builtOn: newKind, params: { ...k.defaults } }));
  }
  // Build a "joiner" shape so we can reuse the TimingVisual.
  const joinerShape = { kind: draft.builtOn, ...draft.params };
  React.useEffect(() => { window.lucide?.createIcons?.(); }, [draft.builtOn]);

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 40,
      background: "rgba(0,0,0,0.65)", display: "grid", placeItems: "center",
    }} onClick={onCancel}>
      <div onClick={(e) => e.stopPropagation()} style={{
        width: 520, maxHeight: "85vh", overflow: "auto",
        background: "var(--surface)", border: "1px solid var(--border)",
        borderRadius: 12, boxShadow: "var(--elev-3)",
      }}>
        <div style={{ padding: "16px 18px", borderBottom: "1px solid var(--border)",
                       display: "flex", alignItems: "center", gap: 10 }}>
          <Icon name="bookmark-plus" size={16} style={{ color: "var(--accent-warm)" }} />
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 14, fontWeight: 600 }}>
              {draft.id ? "Edit joiner" : "New joiner"}
            </div>
            <div style={{ fontSize: 11, color: "var(--text-dim)" }}>
              A reusable preset built on top of a kind, with your own param defaults.
            </div>
          </div>
          <Button kind="ghost" size="icon" onClick={onCancel}><Icon name="x" size={14} /></Button>
        </div>

        <div style={{ padding: 18, display: "flex", flexDirection: "column", gap: 16 }}>
          <Field label="Name">
            <TextInput value={draft.name}
                        onChange={(v) => setDraft(d => ({ ...d, name: v }))}
                        placeholder="e.g. Brand wipe · 0.5s" />
          </Field>
          <Field label="Built on">
            <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
              {FA_DATA.JOINER_KINDS.filter(k => k.kind !== "none").map(k => {
                const active = draft.builtOn === k.kind;
                return (
                  <button key={k.kind} onClick={() => setBuiltOn(k.kind)} style={{
                    display: "inline-flex", alignItems: "center", gap: 5,
                    padding: "5px 10px", borderRadius: 6,
                    background: active ? "rgba(255,75,75,0.08)" : "var(--surface-2)",
                    border: `1px solid ${active ? "var(--accent)" : "var(--border)"}`,
                    color: active ? "var(--text)" : "var(--text-muted)",
                    fontFamily: "inherit", fontSize: 11.5, fontWeight: 600, cursor: "pointer",
                  }}><Icon name={k.icon} size={11} /> {k.label}</button>
                );
              })}
            </div>
          </Field>
          <div style={{ fontSize: 11.5, color: "var(--text-muted)", lineHeight: 1.5,
                          padding: "8px 12px", background: "var(--surface-2)",
                          border: "1px solid var(--border)", borderRadius: 6 }}>{kind.desc}</div>

          {(draft.builtOn === "fade_through_black" || draft.builtOn === "dip_to_color") && (
            <TimingVisual joiner={joinerShape} kind={kind} />
          )}

          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {kind.params.map(p => (
              <ParamControl key={p.id} param={p}
                             value={draft.params[p.id] ?? p.default}
                             onChange={(v) => setParam(p.id, v)} />
            ))}
          </div>
        </div>

        <div style={{ padding: "12px 18px", borderTop: "1px solid var(--border)",
                       display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <Button kind="ghost" size="sm" onClick={onCancel}>Cancel</Button>
          <Button kind="primary" size="sm" disabled={!draft.name.trim()}
                  onClick={() => onSave({
                    ...draft,
                    id: draft.id || `uj-${Date.now()}`,
                    name: draft.name.trim(),
                  })}>
            {draft.id ? "Save changes" : "Create preset"}
          </Button>
        </div>
      </div>
    </div>
  );
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

Object.assign(window, { OutputTab, ForgeTab, JoinersTab, Toggle });


export { ChapterMarkersCard, ForgePanel, ForgeTab, JoinersTab, OutputChannelsCard, OutputTab, ResolutionPicker, Toggle, UserJoinerAuthor };
