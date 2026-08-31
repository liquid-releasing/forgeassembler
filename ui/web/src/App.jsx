/* @esm-converted */
import React from 'react';
import { FAAcceptBar, FAStatusBar, FATabBody, FATabStrip, FATopBar, fmtTotal } from './AppShell';
import { BuildTab, ClipEditor, Divider } from './BuildTab';
import { Inspector } from './Inspector';
import { JoinerEditor, SavePresetPrompt } from './JoinerEditor';
import { ForgeTab, JoinersTab, OutputTab } from './OtherTabs';
import { HomeScreen } from './HomeScreen';
import { PreviewBand } from './PreviewBand';
import { OpenProjectDialog, SaveAsDialog, UnsavedChangesDialog } from './ProjectIO';
import { Section, TitleEditor } from './TitleEditor';
import { FA_DATA } from './data';
import { loadProject, saveProject, pickFolder, pickFile, detectFolder, probeDuration,
         forgeProject, onForgeProgress, revealPath, validateProject,
         importForgeBundle } from './api/forge';
import { fromForgeProject, toForgeProject, fromDetected, fromForgeBundleSegment } from './lib/projectAdapter';
import { parseProgressLine } from './lib/forgeProgress';
import { DragDropProvider, reorderClipInProject, reorderSectionInProject } from './dragdrop';
import { TweakRadio, TweakSection, TweakToggle, TweaksPanel, useTweaks } from './tweaks-panel';

const { useState, useEffect, useMemo, useRef } = React;

// Tweak defaults — edit-mode markers so the host can persist changes.
const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "buildLayout": "sections",
  "density": "comfortable",
  "joinerStyle": "divider",
  "inspectorMode": "right",
  "sectionGrouping": true,
  "sampleSize": "medium"
}/*EDITMODE-END*/;

// A brand-new, empty project — the state the app boots into. The
// fixtures in data.js are design-time material for the Tweaks panel;
// booting into one showed every user a compilation they never made,
// whose segments point at files that don't exist.
function emptyProject() {
  return {
    name: 'untitled',
    output: { folder: null, resolution: '1080p', quality: 'medium',
              frameRate: 'source', normalizeAudio: true, video: true, funscripts: true },
    channels: { main: true, multi_axis: false, estim_3p: false, estim_4p: false,
                prostate: false, pulse_freq: false, audio_estim: true },
    sections: [{ id: `sec-${Date.now()}`, title: '', color: '#ff8c42',
                 joiner: { type: 'none' }, segments: [], overlays: [] }],
    audioBeds: [],
    userJoiners: [], userGlyphs: [], userTitleTemplates: [],
  };
}

function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [tab, setTab] = useState("home");
  // Multi-select model. `selectedIds` is the current selection set;
  // `selectionAnchor` is the last clip clicked without modifiers — used
  // as the pivot for shift-range expansion.
  const [selectedIds, setSelectedIds]         = useState([]);
  const [selectionAnchor, setSelectionAnchor] = useState(null);
  const [expandedId, setExpandedId] = useState(null);
  const [selectedBedId, setSelectedBedId] = useState(null);
  const [editingClip, setEditingClip] = useState(null); // segment open in the ClipEditor dialog
  const [forging, setForging] = useState(false);
  const [progress, setProgress] = useState(0);
  const [forgeStage, setForgeStage] = useState(null); // live progress line from the backend

  const baseProject = useMemo(() => FA_DATA.PROJECTS[t.sampleSize] || FA_DATA.PROJECTS.medium, [t.sampleSize]);

  // Editable project state. Starts empty; Home's New / Open / recents
  // fill it with the user's own work.
  const [project, setProject] = useState(emptyProject);
  // Swapping Tweaks → Sample project loads a fixture for design work.
  // Skip the mount pass so a fresh launch keeps the empty project.
  const sampleLoaded = useRef(false);
  useEffect(() => {
    if (!sampleLoaded.current) { sampleLoaded.current = true; return; }
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
  const [dirty,         setDirty]         = useState(false);  // empty project: nothing to lose yet
  const [lastSavedAtMs, setLastSavedAtMs] = useState(null);
  const [ioDialog,      setIoDialog]      = useState(null);
  const [pendingAfterSave, setPendingAfterSave] = useState(null);
  const [ioError,       setIoError]       = useState(null);

  // ── Recent projects (localStorage-backed) ──────────────────────
  // Real history, not mock rows: every successful Open / Save-As pushes the
  // path here so the Home screen can reopen it. Capped + de-duped by path.
  const [recents, setRecents] = useState(() => {
    try { return JSON.parse(localStorage.getItem('fa.recentProjects')) || []; }
    catch { return []; }
  });
  function pushRecent(path, name) {
    if (!path) return;
    setRecents(prev => {
      const next = [{ path, name: name || path.replace(/\\/g, '/').split('/').pop(), at: Date.now() },
                    ...prev.filter(r => r.path !== path)].slice(0, 8);
      try { localStorage.setItem('fa.recentProjects', JSON.stringify(next)); } catch { /* ignore */ }
      return next;
    });
  }

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

  // ── Add a new (empty) section ──────────────────────────────────
  // A section's leading transition IS its joiner — so a second section is what
  // creates an editable joiner between it and the one before. New sections
  // start with a "none" joiner (a hard cut); click the joiner to change it.
  function handleAddSection() {
    markDirty();
    const id = `sec-${Date.now()}`;
    setProject(p => ({
      ...p,
      sections: [...p.sections, {
        id, title: '', color: '#ff8c42',
        joiner: { type: 'none' }, segments: [], overlays: [],
      }],
    }));
  }

  // ── Add a transition between two clips ─────────────────────────
  // The "+" between clips. Splits the host section right after `clipId` into a
  // new section that carries the trailing clips, then opens the joiner editor
  // on that new boundary so the user picks the transition. (Joiners only exist
  // between sections, so a transition between clips IS a section split.)
  function handleAddTransition(sectionId, clipId, anchorRect) {
    const newId = `sec-${Date.now()}`;
    setProject(p => {
      const sections = [];
      for (const s of p.sections) {
        if (s.id !== sectionId) { sections.push(s); continue; }
        const i = s.segments.findIndex(seg => seg.id === clipId);
        if (i < 0 || i >= s.segments.length - 1) { sections.push(s); continue; }
        const after = s.segments.slice(i + 1);
        sections.push({ ...s, segments: s.segments.slice(0, i + 1) });
        sections.push({
          id: newId, title: after[0]?.title || '', color: '#ff8c42',
          joiner: { type: 'none' }, segments: after, overlays: [],
        });
      }
      return { ...p, sections };
    });
    markDirty();
    if (anchorRect) setEditingJoiner({ sectionId: newId, anchorRect });
  }

  // ── Remove a section ───────────────────────────────────────────
  // Keeps at least one section. Clears selection (a selected clip may have
  // lived in the removed section).
  function handleRemoveSection(sectionId) {
    setProject(p => {
      if (p.sections.length <= 1) return p;
      return { ...p, sections: p.sections.filter(s => s.id !== sectionId) };
    });
    markDirty();
    clearClipSelection();
    setSelectedBedId(null);
  }

  // ── New (empty) project ────────────────────────────────────────
  // Clears the canvas to a single empty section — the starting point for
  // building a compilation from scratch (Add folder / Add .forge scene).
  function handleNewProject() {
    setProject(emptyProject());
    setSavedPath(null);
    setDirty(true);
    setLastSavedAtMs(null);
    clearClipSelection();
    setSelectedBedId(null);
    setIoError(null);
    setTab('build');
  }

  // ── Home / launcher navigation ─────────────────────────────────
  function goHome() { setTab('home'); }
  // Reopen a recent project. Honours the unsaved-changes guard the same way
  // the topbar Open does.
  function openRecent(r) {
    if (!r?.path) return;
    if (dirty) {
      setPendingAfterSave(() => () => handleOpenProject({ path: r.path, name: r.name }));
      setIoDialog('unsaved-then-open');
    } else {
      handleOpenProject({ path: r.path, name: r.name });
    }
  }

  // ── Output / channel field setters (Output tab) ────────────────
  function setOutput(partial) {
    setProject(p => ({ ...p, output: { ...p.output, ...partial } }));
    markDirty();
  }
  function setChannels(partial) {
    setProject(p => ({ ...p, channels: { ...p.channels, ...partial } }));
    markDirty();
  }

  // ── Project I/O actions ────────────────────────────────────────
  // Save flow:
  //   • If no savedPath  → open Save As dialog
  //   • Else save in place (mocked) → clear dirty, update lastSavedAt
  function handleSaveClick() {
    if (!savedPath) { setIoDialog("save"); return; }
    if (!dirty) return; // no-op
    saveInPlace();
  }
  async function saveInPlace() {
    if (!savedPath) { setIoDialog("save"); return; }
    try {
      await saveProject(savedPath, toForgeProject(project, { folder: project.output?.folder }));
      setDirty(false);
      setLastSavedAtMs(Date.now());
    } catch (e) {
      console.error('[save] failed', e);
      setIoError(`Couldn't save ${savedPath}: ${e?.message || e}`);
    }
  }
  async function handleSaveAsCommit({ path, basename, folder }) {
    // Stamp the chosen basename + folder onto the project, write it, then
    // adopt the new path. Build the next vm explicitly so the write doesn't
    // race React's async setState.
    const nextVm = {
      ...project,
      name: basename || project.name,
      output: { ...project.output, folder: folder ?? project.output?.folder },
    };
    try {
      await saveProject(path, toForgeProject(nextVm, { folder }));
      setProject(nextVm);
      setSavedPath(path);
      setDirty(false);
      setLastSavedAtMs(Date.now());
      pushRecent(path, nextVm.name);
      setIoDialog(null);
      // If we were saving en route to opening another project, continue.
      if (pendingAfterSave) { const a = pendingAfterSave; setPendingAfterSave(null); a(); }
    } catch (e) {
      console.error('[save] failed', e);
      setIoError(`Couldn't save ${path}: ${e?.message || e}`);
    }
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
  async function handleOpenProject({ path, name }) {
    // Real load: read the .forgeproject.json via the bridge and adapt the
    // snake_case schema into the camelCase view-model. loadProject() returns
    // null when there's no backend (browser mock) — fall back to a name stamp
    // so `npm run dev` still demos the flow.
    setIoDialog(null);
    setIoError(null);
    try {
      const json = await loadProject(path);
      if (!json) { // mock / no backend
        setSavedPath(path);
        setProject(p => ({ ...p, name: name || p.name }));
        setDirty(false);
        setLastSavedAtMs(Date.now());
        pushRecent(path, name);
        setTab('build');
        return;
      }
      const vm = fromForgeProject(json);
      setProject(vm);
      setSavedPath(path);
      setDirty(false);
      setLastSavedAtMs(Date.now());
      pushRecent(path, vm.name || name);
      setTab('build');
    } catch (e) {
      console.error('[open] failed', e);
      setIoError(`Couldn't open ${path}: ${e?.message || e}`);
    }
  }

  // ── Add clips from a folder (detect → append) ──────────────────
  // Picks a folder, scans it for clips + sidecar funscripts/audio-estim,
  // and appends the detected segments to the target section (or the last
  // section, or a fresh one). Video durations are probed lazily after the
  // segments land so the list paints immediately.
  // Append segments to a target section (or the last/new one), then probe
  // video durations. The chapter NAME defaults to the first added clip's name
  // when the section is still unnamed — so a clip's filename becomes its
  // chapter by default (the user can rename it).
  function appendSegments(segs, sectionId) {
    if (!segs.length) return;
    const stamp = Date.now();
    markDirty();
    setProject(p => {
      const sections = p.sections.length ? p.sections : [{
        id: `sec-${stamp}`, title: '', color: '#ff8c42',
        joiner: { type: 'none' }, segments: [], overlays: [],
      }];
      const targetId = sectionId || sections[sections.length - 1].id;
      return {
        ...p,
        sections: sections.map(s => s.id === targetId
          ? { ...s, title: s.title || segs[0]?.title || '', segments: [...s.segments, ...segs] }
          : s),
      };
    });
    for (const seg of segs) {
      if (seg.kind === 'still' || !seg.file) continue;
      probeDuration(seg.file).then(ms => {
        if (!ms) return;
        setProject(p => ({
          ...p,
          sections: p.sections.map(s => ({
            ...s,
            segments: s.segments.map(x => x.id === seg.id ? { ...x, durMs: ms } : x),
          })),
        }));
      }).catch(() => { /* leave durMs at 0 if probe fails */ });
    }
  }

  // ── Add clips from a FOLDER (batch detect) — the header "Add folder…" ──
  async function handleAddClips(sectionId) {
    setIoError(null);
    const folder = await pickFolder();
    if (!folder) return;
    let payload;
    try {
      payload = await detectFolder(folder);
    } catch (e) {
      console.error('[detect] failed', e);
      setIoError(`Couldn't scan ${folder}: ${e?.message || e}`);
      return;
    }
    const stamp = Date.now();
    const newSegs = fromDetected(payload).map((s, i) => ({ ...s, id: `${s.id}-${stamp}-${i}` }));
    if (!newSegs.length) {
      setIoError(`No clips found in ${folder}.`);
      return;
    }
    appendSegments(newSegs, sectionId);
  }

  // ── Add ONE clip — a video file OR a .forge scene (per-section "Add clip") ──
  async function handleAddClip(sectionId) {
    setIoError(null);
    const path = await pickFile({
      title: 'Add a clip — pick a video or a .forge scene',
      filterName: 'Video or .forge scene',
      extensions: ['mp4', 'mov', 'mkv', 'webm', 'm4v', 'avi', 'forge'],
    });
    if (!path) return;
    if (/\.forge$/i.test(path)) {
      await importForgeBundleToSection(path, sectionId);
      return;
    }
    const stamp = Date.now();
    const base = path.replace(/\\/g, '/').split('/').pop();
    const stem = base.replace(/\.[^.]+$/, '');
    const isStill = /\.(png|jpe?g|webp)$/i.test(path);
    appendSegments([{
      id: `seg-${stem}-${stamp}`, file: path, title: stem,
      kind: isStill ? 'still' : 'video',
      durMs: isStill ? 5000 : 0, channels: [], overlays: 0, overlaysList: [],
      audio: 'keep', temp: 0, funscriptsSource: 'auto_detect', explicitFunscripts: {},
    }], sectionId);
  }

  // Import a `.forge` bundle into a section: explicit channel map, with a
  // relink prompt when the lean bundle carries no media. Shared by the
  // "Add .forge scene…" header button and the per-section "Add clip".
  async function importForgeBundleToSection(bundle, sectionId) {
    let payload;
    try {
      payload = await importForgeBundle(bundle);
    } catch (e) {
      console.error('[import-forge] failed', e);
      setIoError(`Couldn't import ${bundle}: ${e?.message || e}`);
      return;
    }
    if (payload?.needs_video) {
      const video = await pickFile({
        title: `Select the source VIDEO for “${payload.stem || 'this scene'}”`,
        filterName: 'Video', extensions: ['mp4', 'mov', 'mkv', 'webm', 'm4v', 'avi'],
      });
      if (!video) {
        setIoError(`Import canceled — “${payload.stem || 'scene'}” needs a source video to relink.`);
        return;
      }
      try {
        payload = await importForgeBundle(bundle, { video });
      } catch (e) {
        console.error('[import-forge] relink failed', e);
        setIoError(`Couldn't relink video: ${e?.message || e}`);
        return;
      }
    }
    const seg = fromForgeBundleSegment(payload?.segment);
    if (!seg) {
      setIoError(`Import produced no segment for ${payload?.stem || bundle}.`);
      return;
    }
    seg.id = `${seg.id || 'seg'}-${Date.now()}`;
    appendSegments([seg], sectionId);
  }

  // ── Add a finished FunscriptForge `.forge` scene (header button) ──
  async function handleAddForgeScene(sectionId) {
    setIoError(null);
    const bundle = await pickFile({
      title: 'Select a .forge scene to import',
      filterName: 'FunscriptForge bundle', extensions: ['forge'],
    });
    if (!bundle) return;
    await importForgeBundleToSection(bundle, sectionId);
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

  // Single-segment edit/remove (used by the ClipEditor dialog).
  function updateSegment(segId, partial) {
    markDirty();
    setProject(p => ({
      ...p,
      sections: p.sections.map(s => ({
        ...s,
        segments: s.segments.map(seg => seg.id === segId ? { ...seg, ...partial } : seg),
      })),
    }));
  }
  function removeSegment(segId) {
    markDirty();
    setProject(p => ({
      ...p,
      sections: p.sections.map(s => ({
        ...s,
        segments: s.segments.filter(seg => seg.id !== segId),
      })),
    }));
    setSelectedIds(prev => prev.filter(id => id !== segId));
  }

  const [pipeline, setPipeline] = useState({
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

  // Real forge: ensure the project is saved to disk, subscribe to the
  // `fa:progress` stream, run `forge`, then reveal the output.
  async function startForge() {
    if (forging) return; // no mid-run cancel yet — button is disabled while forging
    let path = savedPath;
    if (!path) { setIoError('Save the project before forging.'); setIoDialog('save'); return; }
    if (dirty) {
      try {
        await saveProject(path, toForgeProject(project, { folder: project.output?.folder }));
        setDirty(false); setLastSavedAtMs(Date.now());
      } catch (e) {
        console.error('[forge] pre-save failed', e);
        setIoError(`Couldn't save before forge: ${e?.message || e}`);
        return;
      }
    }

    // Pre-flight validation — refuse to forge an invalid project. Warnings
    // are non-fatal; only hard errors block. (validateProject is a no-op in
    // the browser mock, returning ok:true.)
    try {
      const v = await validateProject(path);
      if (v && v.ok === false && Array.isArray(v.errors) && v.errors.length) {
        const head = v.errors.slice(0, 3).join('; ');
        setIoError(`Can't forge — ${v.errors.length} problem${v.errors.length === 1 ? '' : 's'}: ${head}${v.errors.length > 3 ? '…' : ''}`);
        return;
      }
    } catch (e) {
      console.warn('[forge] validation unavailable, continuing', e);
    }

    // Progress model: every backend stage claims an equal slice of the
    // bar, and each stage fills its own slice from ffmpeg's `time=`
    // reports measured against the output duration the CLI sends up
    // front. Stage ticks alone left the bar parked at one third for the
    // whole encode — the only part that takes minutes.
    //
    // The count below is a guess from our copy of the project, used only
    // until the CLI's `meta:` line tells us how many stages it will
    // actually run.
    let stageCount = Math.max(1,
      (project.output?.video !== false ? 1 : 0) +
      (project.output?.funscripts !== false ? 1 : 0) +
      (project.channels?.audio_estim ? 1 : 0));
    let stage = 0;          // 1-based index of the stage in flight
    let durationMs = 0;     // output length, from the CLI's `meta:` line
    let shown = 0;          // last value pushed — the bar never walks back
    const advance = (frac) => {
      const v = Math.min(0.95,
        (Math.max(0, stage - 1) + Math.min(1, Math.max(0, frac))) / stageCount);
      if (v > shown) { shown = v; setProgress(v); }
    };

    setIoError(null);
    setForging(true); setProgress(0); setForgeStage('Starting…');
    let unlisten = () => {};
    try {
      unlisten = await onForgeProgress((line) => {
        const ev = parseProgressLine(line);
        if (!ev) return;
        if (ev.kind === 'meta') {
          if (ev.durationMs) durationMs = ev.durationMs;
          if (ev.stages) stageCount = Math.max(1, ev.stages);
          return;
        }
        if (ev.kind === 'stage') {
          stage = Math.min(stageCount, stage + 1);
          advance(0);
          setForgeStage(ev.text);
          return;
        }
        if (ev.kind === 'done') { setForgeStage('Finishing…'); return; }
        // 'encoded' — ffmpeg told us how much of the output exists.
        if (durationMs > 0) advance(ev.ms / durationMs);
      });
      const summaryStr = await forgeProject(path, {});
      let summary = null;
      try { summary = JSON.parse(summaryStr); } catch { /* non-JSON summary */ }
      shown = 1; setProgress(1); setForgeStage('Done');
      accept('forge');
      const reveal = summary?.video || project.output?.folder;
      if (reveal) revealPath(reveal).catch(() => {});
    } catch (e) {
      console.error('[forge] failed', e);
      setIoError(`Forge failed: ${e?.message || e}`);
      setForgeStage(null);
    } finally {
      unlisten();
      setForging(false);
    }
  }

  // ─── Tab body ──────────────────────────────────────────────────
  let body, acceptKey = null, acceptSummary = "", acceptLabel = "Accept and chain";

  if (tab === "home") {
    body = (
      <HomeScreen
        recents={recents}
        hasWork={flatSegments.length > 0}
        projectName={project.name}
        segCount={flatSegments.length}
        sectionCount={project.sections.length}
        totalLabel={fmtTotal(totalMs)}
        onNew={handleNewProject}
        onOpen={handleOpenClick}
        onOpenRecent={openRecent}
        onContinue={() => setTab('build')} />
    );
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
                onAddClips={handleAddClips}
                onAddClip={handleAddClip}
                onAddForgeScene={handleAddForgeScene}
                onAddSection={handleAddSection}
                onRemoveSection={handleRemoveSection}
                onEditClip={(seg) => setEditingClip(seg)}
                onAddTransition={handleAddTransition}
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
                       onSetChannelGapPolicy={setChannelGap}
                       onSetOutput={setOutput}
                       onSetChannels={setChannels} />;
    acceptKey = "output";
    acceptSummary = `Resolution ${project.output.resolution} · loudness ${project.output.normalizeAudio ? "−16 LUFS" : "off"}.`;
  } else if (tab === "forge") {
    body = <ForgeTab project={project} totalMs={totalMs} onForge={startForge} forging={forging} progress={progress} forgeStage={forgeStage} />;
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
                 onOpen={handleOpenClick} onSave={handleSaveClick} onNew={handleNewProject}
                 onHome={goHome} />
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

      {/* Open/save error toast */}
      {ioError && (
        <div style={{
          position: "fixed", bottom: 56, left: "50%", transform: "translateX(-50%)",
          zIndex: 60, maxWidth: 560,
          display: "flex", alignItems: "center", gap: 10,
          padding: "10px 14px", borderRadius: 8,
          background: "var(--surface)", border: "1px solid var(--danger)",
          boxShadow: "var(--elev-3)", color: "var(--text)", fontSize: 12.5,
        }}>
          <span style={{ flex: 1 }}>{ioError}</span>
          <button onClick={() => setIoError(null)}
                  style={{ background: "transparent", border: "none", color: "var(--text-dim)",
                           cursor: "pointer", fontFamily: "inherit", fontSize: 12 }}>Dismiss</button>
        </div>
      )}

      {/* Clip editor (trim · audio · remove) */}
      {editingClip && (
        <ClipEditor
          seg={editingClip}
          onSave={updateSegment}
          onRemove={removeSegment}
          onClose={() => setEditingClip(null)} />
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
