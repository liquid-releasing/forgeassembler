/* @esm-converted */
import React from 'react';
import { FAAcceptBar, FAStatusBar, FATabBody, FATabStrip, FATopBar, fmtTotal } from './AppShell';
import { BuildTab, Divider } from './BuildTab';
import { Inspector } from './Inspector';
import { JoinerEditor, SavePresetPrompt } from './JoinerEditor';
import { ForgeTab, JoinersTab, OutputTab, ProjectTab } from './OtherTabs';
import { PreviewBand } from './PreviewBand';
import { OpenProjectDialog, SaveAsDialog, UnsavedChangesDialog } from './ProjectIO';
import { Section, TitleEditor } from './TitleEditor';
import { FA_DATA } from './data';
import { DragDropProvider, reorderClipInProject, reorderSectionInProject } from './dragdrop';
import { TweakRadio, TweakSection, TweakToggle, TweaksPanel, useTweaks } from './tweaks-panel';

const { useState, useEffect, useMemo } = React;

// Tweak defaults — edit-mode markers so the host can persist changes.
const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "buildLayout": "sections",
  "density": "comfortable",
  "joinerStyle": "divider",
  "inspectorMode": "right",
  "sectionGrouping": true,
  "sampleSize": "medium"
}/*EDITMODE-END*/;

function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [tab, setTab] = useState("build");
  // Multi-select model. `selectedIds` is the current selection set;
  // `selectionAnchor` is the last clip clicked without modifiers — used
  // as the pivot for shift-range expansion.
  const [selectedIds, setSelectedIds]         = useState(["m3"]);
  const [selectionAnchor, setSelectionAnchor] = useState("m3");
  const [expandedId, setExpandedId] = useState(null);
  const [selectedBedId, setSelectedBedId] = useState(null);
  const [forging, setForging] = useState(false);
  const [progress, setProgress] = useState(0.32);

  const baseProject = useMemo(() => FA_DATA.PROJECTS[t.sampleSize] || FA_DATA.PROJECTS.medium, [t.sampleSize]);

  // Editable project state — deep-cloned from the sample so the user
  // can change joiners + user-joiners and see the result.
  const [project, setProject] = useState(() => structuredClone(baseProject));
  useEffect(() => {
    setProject(structuredClone(baseProject));
    // New sample loaded — reset I/O state to "fresh unsaved" so the
    // user sees the Save-As flow on first save.
    setSavedPath(null);
    setLastSavedAtMs(null);
    setDirty(true);
  }, [baseProject]);

  // Joiner being edited: { sectionId, anchorRect } | null.
  const [editingJoiner, setEditingJoiner] = useState(null);
  // Save-as-preset prompt staged from inside the editor.
  const [savePresetFor, setSavePresetFor] = useState(null);
  // Title editor state. Two pieces of context to disambiguate intent:
  //   anchorClipId   — the clip the user is positioning relative to.
  //                    When set, the editor offers Before / After / End.
  //                    For overlays, this is also the clip the overlay
  //                    is attached to.
  //   forSectionId   — explicitly target this section (for "append to
  //                    section X" from a section-header button).
  const [titleEditor, setTitleEditor] = useState(null);

  // ── Project file I/O state ─────────────────────────────────────
  //   savedPath        absolute path of the .forgeproject.json on disk;
  //                    null = unsaved (new project)
  //   dirty            user edits since last save
  //   lastSavedAtMs    epoch ms of last successful save
  //   ioDialog         "save" | "open" | "unsaved-then-open" | null
  //   pendingAfterSave function() — what to do once dirty is resolved
  const [savedPath,     setSavedPath]     = useState(null);
  const [dirty,         setDirty]         = useState(true);   // demo starts dirty
  const [lastSavedAtMs, setLastSavedAtMs] = useState(null);
  const [ioDialog,      setIoDialog]      = useState(null);
  const [pendingAfterSave, setPendingAfterSave] = useState(null);

  // Tick once a minute so the "saved 2 min ago" label keeps pace.
  const [, setTickerNow] = useState(Date.now());
  useEffect(() => {
    const id = setInterval(() => setTickerNow(Date.now()), 30 * 1000);
    return () => clearInterval(id);
  }, []);

  function markDirty() { setDirty(true); }

  function updateSectionJoiner(sectionId, newJoiner) {
    setProject(p => ({
      ...p,
      sections: p.sections.map(s => s.id === sectionId ? { ...s, joiner: newJoiner } : s),
    }));
    markDirty();
  }
  function renameSection(sectionId, newTitle) {
    setProject(p => ({
      ...p,
      sections: p.sections.map(s => s.id === sectionId ? { ...s, title: newTitle } : s),
    }));
    markDirty();
  }
  function addUserJoiner(payload) {
    setProject(p => ({ ...p, userJoiners: [...(p.userJoiners || []), payload] }));
    markDirty();
  }
  function addUserTemplate(payload) {
    setProject(p => ({ ...p, userTitleTemplates: [...(p.userTitleTemplates || []), payload] }));
    markDirty();
  }
  function addUserGlyph(payload) {
    setProject(p => ({ ...p, userGlyphs: [...(p.userGlyphs || []), payload] }));
    markDirty();
  }
  function updateUserJoiner(payload) {
    setProject(p => ({
      ...p,
      userJoiners: (p.userJoiners || []).map(u => u.id === payload.id ? payload : u),
    }));
    markDirty();
  }
  function removeUserJoiner(id) {
    setProject(p => ({ ...p, userJoiners: (p.userJoiners || []).filter(u => u.id !== id) }));
    markDirty();
  }
  function reorderClip(clipId, fromSectionId, toSectionId, anchorClipId, position) {
    setProject(p => reorderClipInProject(p, clipId, fromSectionId, toSectionId, anchorClipId, position));
    markDirty();
  }
  function reorderSection(sectionId, anchorSectionId, position) {
    setProject(p => reorderSectionInProject(p, sectionId, anchorSectionId, position));
    markDirty();
  }
  // Title save dispatcher. Branches on payload.useAs + ctx.
  function applyTitlePayload(payload, ctx) {
    if (payload.useAs === "overlay" && ctx?.anchorClipId) {
      addTitleAsOverlay(payload, ctx.anchorClipId);
    } else {
      addTitleAsSegment(payload, ctx);
    }
  }

  function addTitleAsOverlay(payload, clipId) {
    markDirty();
    const overlay = {
      id: `ov-${Date.now()}`,
      kind: "title",
      file: `overlay-${slug(payload.title)}.png`,
      thumb: payload.overlayThumb || payload.thumb,
      position: payload.overlayPosition || "center",
      startS: payload.overlayStartS,
      fadeInS: payload.overlayFadeInS,
      fadeOutS: payload.overlayFadeOutS,
      opacity: payload.overlayOpacity,
      title: titleMeta(payload),
    };
    setProject(p => ({
      ...p,
      sections: p.sections.map(s => ({
        ...s,
        segments: s.segments.map(seg => seg.id !== clipId ? seg : {
          ...seg,
          overlaysList: [...(seg.overlaysList || []), overlay],
          overlays: (seg.overlaysList || []).length + 1,
        }),
      })),
    }));
  }

  function addTitleAsSegment(payload, ctx) {
    markDirty();
    const seg = {
      id: `seg-title-${Date.now()}`,
      title: payload.title || "Title card",
      file: `title-${slug(payload.title)}.png`,
      kind: "still",
      durMs: Math.round((payload.durationS || 5) * 1000),
      thumb: payload.thumb,
      channels: [],
      overlays: 0,
      audio: "silence",
      temp: 0,
      titleCard: titleMeta(payload),
    };
    setProject(p => ({
      ...p,
      sections: p.sections.map(s => {
        // Anchored-to-clip insertion takes precedence.
        if (ctx?.anchorClipId) {
          const idx = s.segments.findIndex(c => c.id === ctx.anchorClipId);
          if (idx === -1) return s;
          const ip = payload.insertionPoint || "after";
          if (ip === "end") return { ...s, segments: [...s.segments, seg] };
          const at = ip === "before" ? idx : idx + 1;
          const next = [...s.segments];
          next.splice(at, 0, seg);
          return { ...s, segments: next };
        }
        // Otherwise append to the explicit section…
        if (ctx?.forSectionId && s.id === ctx.forSectionId) {
          return { ...s, segments: [...s.segments, seg] };
        }
        // …or to the last section.
        if (!ctx?.forSectionId && s.id === p.sections[p.sections.length - 1].id) {
          return { ...s, segments: [...s.segments, seg] };
        }
        return s;
      }),
    }));
  }

  function titleMeta(p) {
    return { layout: p.layout, theme: p.theme, title: p.title,
              eyebrow: p.eyebrow, subtitle: p.subtitle, showGlyph: p.showGlyph };
  }
  function slug(s) { return (s || "untitled").toLowerCase().replace(/\s+/g, "-"); }

  // ── Project I/O actions ────────────────────────────────────────
  // Save flow:
  //   • If no savedPath  → open Save As dialog
  //   • Else save in place (mocked) → clear dirty, update lastSavedAt
  function handleSaveClick() {
    if (!savedPath) { setIoDialog("save"); return; }
    if (!dirty) return; // no-op
    saveInPlace();
  }
  function saveInPlace() {
    setDirty(false);
    setLastSavedAtMs(Date.now());
  }
  function handleSaveAsCommit({ path, basename }) {
    setSavedPath(path);
    setProject(p => ({ ...p, name: basename || p.name }));
    setDirty(false);
    setLastSavedAtMs(Date.now());
    setIoDialog(null);
    // If we were saving en route to opening another project, continue.
    if (pendingAfterSave) { const a = pendingAfterSave; setPendingAfterSave(null); a(); }
  }
  // Open flow:
  //   • If dirty → "Save changes?" first, with a continuation
  //   • Otherwise → open dialog right away
  function handleOpenClick() {
    if (dirty) {
      setPendingAfterSave(() => () => setIoDialog("open"));
      setIoDialog("unsaved-then-open");
    } else {
      setIoDialog("open");
    }
  }
  function handleDiscardAndOpen() {
    setPendingAfterSave(null);
    setIoDialog("open");
  }
  function handleOpenProject({ path, name }) {
    // For the prototype this re-loads the current sample but stamps it
    // with the picked name / path. A real implementation would parse
    // the JSON, rebuild project state, and restore selection.
    setSavedPath(path);
    setProject(p => ({ ...p, name }));
    setDirty(false);
    setLastSavedAtMs(Date.now() - 60_000); // pretend it was saved a minute ago
    setIoDialog(null);
  }

  // Reset selection if it doesn't exist in the new sample
  useEffect(() => {
    const flat = project.sections.flatMap(s => s.segments);
    const flatIds = flat.map(s => s.id);
    const stillValid = selectedIds.filter(id => flatIds.includes(id));
    if (stillValid.length !== selectedIds.length) {
      const fallback = flat[1]?.id || flat[0]?.id ? [flat[1]?.id || flat[0]?.id] : [];
      setSelectedIds(stillValid.length ? stillValid : fallback);
      setSelectionAnchor(stillValid[0] || fallback[0] || null);
    }
    if (selectedBedId && !project.audioBeds.find(b => b.id === selectedBedId)) setSelectedBedId(null);
  }, [project]);

  const flatSegments = project.sections.flatMap(s => s.segments);
  const totalMs = flatSegments.reduce((a, s) => a + s.durMs, 0);
  const selectedSegs = flatSegments.filter(s => selectedIds.includes(s.id));
  const selectedSeg  = selectedSegs.length === 1 ? selectedSegs[0] : null;
  const selectedBed  = project.audioBeds.find(b => b.id === selectedBedId) || null;

  // Click handler shared by every clip row.
  // Modifier keys: shift = range from anchor; cmd/ctrl = toggle in/out.
  function selectClip(id, e) {
    setSelectedBedId(null);
    const flatIds = flatSegments.map(s => s.id);
    if (e?.shiftKey && selectionAnchor && flatIds.includes(selectionAnchor)) {
      const aIdx = flatIds.indexOf(selectionAnchor);
      const bIdx = flatIds.indexOf(id);
      const [lo, hi] = aIdx < bIdx ? [aIdx, bIdx] : [bIdx, aIdx];
      setSelectedIds(flatIds.slice(lo, hi + 1));
    } else if (e?.metaKey || e?.ctrlKey) {
      setSelectedIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
      setSelectionAnchor(id);
    } else {
      setSelectedIds([id]);
      setSelectionAnchor(id);
    }
  }
  function clearClipSelection() { setSelectedIds([]); setSelectionAnchor(null); }

  // Bulk operations. All apply to the current `selectedIds`.
  function bulkUpdate(partial) {
    markDirty();
    const ids = selectedIds;
    setProject(p => ({
      ...p,
      sections: p.sections.map(s => ({
        ...s,
        segments: s.segments.map(seg => ids.includes(seg.id) ? { ...seg, ...partial } : seg),
      })),
    }));
  }
  function bulkDuplicate() {
    markDirty();
    const ids = selectedIds;
    setProject(p => ({
      ...p,
      sections: p.sections.map(s => {
        const next = [];
        for (const seg of s.segments) {
          next.push(seg);
          if (ids.includes(seg.id)) {
            next.push({ ...seg, id: `${seg.id}-dup-${Date.now()}-${Math.random().toString(36).slice(2,6)}`,
                         title: seg.title + " (copy)" });
          }
        }
        return { ...s, segments: next };
      }),
    }));
  }
  function bulkRemove() {
    markDirty();
    const ids = selectedIds;
    setProject(p => ({
      ...p,
      sections: p.sections.map(s => ({
        ...s,
        segments: s.segments.filter(seg => !ids.includes(seg.id)),
      })),
    }));
    clearClipSelection();
  }

  const [pipeline, setPipeline] = useState({
    project:  { accepted: true,  chainFile: "project.ffmeta.json" },
    build:    { accepted: false, chainFile: "_build.forgeproject.json" },
    output:   { accepted: false, chainFile: "_output.json" },
    forge:    { accepted: false, chainFile: "forged/" + project.name + ".mp4" },
  });

  // Per-channel "what to do at the gaps" policy. Defaults to "blank"
  // (don't synthesise anything for clips that lack this channel).
  const [channelGapPolicy, setChannelGapPolicy] = useState({});
  const setChannelGap = (id, v) => setChannelGapPolicy(p => ({ ...p, [id]: v }));

  // re-derive chainFile when project changes
  useEffect(() => {
    setPipeline(p => ({
      ...p,
      forge: { ...p.forge, chainFile: "forged/" + project.name + ".mp4" },
    }));
  }, [project.name]);

  useEffect(() => { window.lucide?.createIcons?.(); });

  // Escape clears the clip selection (handy after a big shift-click run).
  useEffect(() => {
    function onKey(e) {
      if (e.key === "Escape" && selectedIds.length > 0) clearClipSelection();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedIds.length]);

  const accept = (key) => setPipeline(p => ({ ...p, [key]: { ...p[key], accepted: true } }));
  const reset  = (key) => setPipeline(p => ({ ...p, [key]: { ...p[key], accepted: false } }));

  function startForge() {
    if (forging) { setForging(false); return; }
    setForging(true); setProgress(0);
    let p = 0;
    const id = setInterval(() => {
      p += 0.012 + Math.random() * 0.02;
      if (p >= 1) { p = 1; clearInterval(id); setForging(false); accept("forge"); }
      setProgress(p);
    }, 220);
  }

  // ─── Tab body ──────────────────────────────────────────────────
  let body, acceptKey = null, acceptSummary = "", acceptLabel = "Accept and chain";

  if (tab === "project") {
    body = <ProjectTab project={project} />;
    acceptKey = "project";
    acceptSummary = `Output folder set · basename "${project.name}".`;
  } else if (tab === "build") {
    acceptKey = "build";
    acceptSummary = `${project.sections.length} sections · ${flatSegments.length} segments · ${project.audioBeds.length} audio bed${project.audioBeds.length === 1 ? "" : "s"} · ${fmtTotal(totalMs)} total.`;
    body = (
      <div style={{ flex: 1, minHeight: 0, display: "flex" }}>
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
          <FATabBody>
            <DragDropProvider
              onReorderClip={reorderClip}
              onReorderSection={reorderSection}>
              <BuildTab
                project={project}
                density={t.density}
                buildLayout={t.buildLayout}
                joinerStyle={t.joinerStyle}
                sectionGrouping={t.sectionGrouping}
                inspectorMode={t.inspectorMode}
                selectedIds={selectedIds}
                onSelect={(id, e) => selectClip(id, e)}
                expandedId={expandedId}
                onToggleExpand={(id) => setExpandedId(e => e === id ? null : id)}
                selectedBedId={selectedBedId}
                onSelectBed={(id) => { setSelectedBedId(id); clearClipSelection(); }}
                onClearSelection={clearClipSelection}
                onEditJoiner={(sectionId, anchorRect) => setEditingJoiner({ sectionId, anchorRect })}
                onRenameSection={renameSection}
                onOpenTitleEditor={(sectionId) => setTitleEditor(
                  sectionId
                    ? { anchorClipId: null, forSectionId: sectionId }
                    : { anchorClipId: selectedSeg?.id || null, forSectionId: null }
                )} />
            </DragDropProvider>
          </FATabBody>
          <PreviewBand project={project} totalMs={totalMs} segCount={flatSegments.length} />
        </div>
        {t.inspectorMode === "right" && (
          <Inspector
            segs={selectedSegs} bed={selectedBed} project={project} mode={t.inspectorMode}
            onClose={() => { clearClipSelection(); setSelectedBedId(null); }}
            onAddOverlay={(clipId) => setTitleEditor({ anchorClipId: clipId, forSectionId: null })}
            onBulkUpdate={bulkUpdate}
            onBulkDuplicate={bulkDuplicate}
            onBulkRemove={bulkRemove} />
        )}
      </div>
    );
  } else if (tab === "output") {
    body = <OutputTab project={project}
                       channelGapPolicy={channelGapPolicy}
                       onSetChannelGapPolicy={setChannelGap} />;
    acceptKey = "output";
    acceptSummary = `Resolution ${project.output.resolution} · loudness ${project.output.normalizeAudio ? "−16 LUFS" : "off"}.`;
  } else if (tab === "forge") {
    body = <ForgeTab project={project} totalMs={totalMs} onForge={startForge} forging={forging} progress={progress} />;
    acceptKey = "forge";
    acceptSummary = forging ? "Forging in progress…" : (pipeline.forge.accepted ? "Forged successfully." : "Press Forge to render the combined output.");
    acceptLabel = "Mark forged";
  } else if (tab === "joiners") {
    body = <JoinersTab project={project}
                         onAddUserJoiner={addUserJoiner}
                         onUpdateUserJoiner={updateUserJoiner}
                         onRemoveUserJoiner={removeUserJoiner} />;
  }

  // ─── Render ─────────────────────────────────────────────────────
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", background: "var(--bg)" }}>
      <FATopBar project={project} totalMs={totalMs}
                 segCount={flatSegments.length} sectionCount={project.sections.length}
                 savedPath={savedPath} dirty={dirty} lastSavedAtMs={lastSavedAtMs}
                 onOpen={handleOpenClick} onSave={handleSaveClick} />
      <FATabStrip active={tab} onChange={setTab} pipeline={pipeline} />

      <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
        {tab === "build" ? body : <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>{body}</div>}
      </div>

      {acceptKey && (
        <FAAcceptBar
          summary={acceptSummary}
          chainFile={pipeline[acceptKey].chainFile}
          accepted={pipeline[acceptKey].accepted}
          primaryLabel={acceptLabel}
          onAccept={() => accept(acceptKey)}
          onReset={() => reset(acceptKey)} />
      )}
      <FAStatusBar activeTab={tab} chainFile={acceptKey ? pipeline[acceptKey].chainFile : null} />

      {/* ── Joiner editor overlay ── */}
      {editingJoiner && (() => {
        const sIdx = project.sections.findIndex(s => s.id === editingJoiner.sectionId);
        const sec = project.sections[sIdx];
        if (!sec) return null;
        const prevSec = project.sections[sIdx - 1];
        const prevClip = prevSec ? prevSec.segments[prevSec.segments.length - 1] : null;
        const nextClip = sec.segments[0] || null;
        return (
          <JoinerEditor
            joiner={sec.joiner}
            userJoiners={project.userJoiners || []}
            prevClip={prevClip}
            nextClip={nextClip}
            anchorRect={editingJoiner.anchorRect}
            onChange={(newJ) => updateSectionJoiner(sec.id, newJ)}
            onClose={() => setEditingJoiner(null)}
            onSaveAsPreset={(j) => setSavePresetFor({ joiner: j })} />
        );
      })()}
      {savePresetFor && (
        <SavePresetPrompt
          joiner={savePresetFor.joiner}
          onCancel={() => setSavePresetFor(null)}
          onSave={(name) => {
            addUserJoiner({
              id: `uj-${Date.now()}`,
              name,
              builtOn: savePresetFor.joiner.kind,
              params: Object.fromEntries(
                Object.entries(savePresetFor.joiner).filter(([k]) => k !== "kind")),
            });
            setSavePresetFor(null);
          }} />
      )}

      {/* ── Title editor modal ── */}
      {titleEditor && (
        <TitleEditor
          selectedSeg={titleEditor.anchorClipId
            ? flatSegments.find(s => s.id === titleEditor.anchorClipId)
            : null}
          userGlyphs={project.userGlyphs || []}
          userTemplates={project.userTitleTemplates || []}
          onAddUserGlyph={addUserGlyph}
          onAddUserTemplate={addUserTemplate}
          onCancel={() => setTitleEditor(null)}
          onSave={(payload) => {
            applyTitlePayload(payload, titleEditor);
            setTitleEditor(null);
          }} />
      )}

      {/* ── Project I/O dialogs ── */}
      {ioDialog === "save" && (
        <SaveAsDialog project={project}
                       defaultFolder={savedPath ? savedPath.replace(/[/\\][^/\\]+$/, "") : null}
                       onCancel={() => { setIoDialog(null); setPendingAfterSave(null); }}
                       onSave={handleSaveAsCommit} />
      )}
      {ioDialog === "open" && (
        <OpenProjectDialog
          onCancel={() => setIoDialog(null)}
          onOpen={handleOpenProject} />
      )}
      {ioDialog === "unsaved-then-open" && (
        <UnsavedChangesDialog
          project={project} savedPath={savedPath}
          onCancel={() => { setIoDialog(null); setPendingAfterSave(null); }}
          onDiscard={handleDiscardAndOpen}
          onSave={() => {
            if (!savedPath) setIoDialog("save");          // route through Save As first
            else { saveInPlace(); setIoDialog("open"); }   // save in place, then open
          }} />
      )}

      {/* ── Tweaks panel ── */}
      <TweaksPanel title="ForgeAssembler · Tweaks">
        <TweakSection label="Build canvas" />
        <TweakRadio  label="Layout"
                      value={t.buildLayout}
                      options={[
                        { value: "sections", label: "Sections" },
                        { value: "flat",     label: "Flat" },
                        { value: "timeline", label: "Timeline" },
                      ]}
                      onChange={(v) => setTweak('buildLayout', v)} />
        <TweakRadio  label="Density"
                      value={t.density}
                      options={[
                        { value: "compact",     label: "Compact" },
                        { value: "comfortable", label: "Comfy" },
                        { value: "roomy",       label: "Roomy" },
                      ]}
                      onChange={(v) => setTweak('density', v)} />
        <TweakToggle label="Section grouping"
                      value={t.sectionGrouping}
                      onChange={(v) => setTweak('sectionGrouping', v)} />

        <TweakSection label="Joiners" />
        <TweakRadio  label="Style"
                      value={t.joinerStyle}
                      options={[
                        { value: "inline-pill", label: "Inline pill" },
                        { value: "divider",     label: "Divider" },
                        { value: "lane",        label: "Lane" },
                      ]}
                      onChange={(v) => setTweak('joinerStyle', v)} />

        <TweakSection label="Inspector" />
        <TweakRadio  label="Mode"
                      value={t.inspectorMode}
                      options={[
                        { value: "right",  label: "Right panel" },
                        { value: "inline", label: "Inline" },
                      ]}
                      onChange={(v) => setTweak('inspectorMode', v)} />

        <TweakSection label="Sample project" />
        <TweakRadio  label="Size"
                      value={t.sampleSize}
                      options={[
                        { value: "small",  label: "S · 4" },
                        { value: "medium", label: "M · 8" },
                        { value: "large",  label: "L · 14" },
                      ]}
                      onChange={(v) => setTweak('sampleSize', v)} />
      </TweaksPanel>
    </div>
  );
}

export { App, TWEAK_DEFAULTS };
