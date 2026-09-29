/* @esm-converted */
import React from 'react';
import { FAAcceptBar, FAStatusBar, FATabBody, FATabStrip, FATopBar, fmtTotal } from './AppShell';
import { BuildTab, ClipEditor } from './BuildTab';
import { Inspector } from './Inspector';
import { JoinerEditor, makeJoinerFromKind } from './JoinerEditor';
import { ForgeTab, OutputTab } from './OtherTabs';
import { ViewerTab } from './ViewerTab';
import { HomeScreen } from './HomeScreen';
import { PreviewBand } from './PreviewBand';
import { CompilationPreview } from './CompilationPreview';
import { Modal, ModalFooter, OpenProjectDialog, SaveAsDialog,
         UnsavedChangesDialog } from './ProjectIO';
import { FA_DATA } from './data';
import { loadProject, saveProject, pickFolder, pickFile, pickSavePath,
         detectForgeFolder, probeDuration,
         forgeProject, onForgeProgress, revealPath, validateProject,
         cancelForge, FORGE_CANCELLED, readJsonFile, writeJsonFile, pathsExist,
         importForgeBundle, extractThumbnail, thumbnailPathFor } from './api/forge';
import { BRANDING_FILTERS, applyBranding, brandingFileName, describeBranding,
         extractBranding, hasBranding, isBrandingDoc } from './lib/branding';
import { Button, Icon } from './primitives';
import { projectDisplayName } from './lib/projectFile';
import { applyRemap, commonRoot, describeMissing, mediaPathsOf,
         planRemap } from './lib/missingMedia';
import { fromForgeProject, toForgeProject, fromForgeBundleSegment,
         projectDurationMs, projectSignature } from './lib/projectAdapter';
import { parseProgressLine, stageProgress, makeStageTracker } from './lib/forgeProgress';
import { markForgedGate } from './lib/forgeGate';
import { DragDropProvider, reorderSectionInProject } from './dragdrop';
import { baseName, lastFolder, parentFolder, rememberBranding, rememberedBranding,
         rememberFolder, rememberFileFolder } from './lib/lastFolders';
import { titleForClip, titleForFolder } from './lib/titleDefaults';

const { useState, useEffect, useMemo, useRef } = React;

// A brand-new, empty project — the state the app boots into.
function emptyProject() {
  return {
    name: 'untitled',
    // `folderLayout: 'grouped'` here and nowhere else. A project LOADED
    // without the field stays flat, so re-forging an old one cannot scatter a
    // second copy of everything into art/ sound/ estim/ haptic/ beside the
    // first. Only new work starts in the new shape.
    output: { folder: null, resolution: '1080p', quality: 'medium',
              frameRate: 'source', normalizeAudio: true, video: true,
              funscripts: true, folderLayout: 'grouped' },
    // Channel flags are VETOES over what the clips actually carry, not an
    // allow-list — the engine forges every DETECTED channel and skips the
    // ones nothing carries. All-on is therefore the correct empty state;
    // all-off-but-main used to reduce a 20-channel scene to one funscript.
    channels: { main: true, multi_axis: true, estim_3p: true, estim_4p: true,
                prostate: true, pulse_freq: true, audio_estim: true },
    sections: [{ id: `sec-${Date.now()}`, title: '', color: '#ff8c42',
                 joiner: { kind: 'none' }, segments: [], overlays: [] }],
  };
}

function App() {
  const [tab, setTab] = useState("home");
  // Selection. One scene at a time: the multi-select model (shift-range,
  // ctrl-toggle) served bulk edits across clips inside a section, and
  // there is no longer any such thing as a section with several clips.
  const [selectedIds, setSelectedIds] = useState([]);
  const [editingClip, setEditingClip] = useState(null); // segment open in the ClipEditor dialog
  const [forging, setForging] = useState(false);
  const [progress, setProgress] = useState(0);
  const [forgeStage, setForgeStage] = useState(null); // live progress line from the backend
  // The signature of the project that was last forged successfully, or null
  // if nothing has been. Compared against the live project to tell a
  // finished render from a stale one — see lib/forgeGate.js.
  const [forgedSig, setForgedSig] = useState(null);
  // Where the last forge actually landed, straight from the summary, so
  // the Viewer opens on THAT file rather than on a path reassembled from
  // the project's name and folder.
  const [forgedPath, setForgedPath] = useState(null);

  // Editable project state. Starts empty; Home's New / Open / recents
  // fill it with the user's own work.
  const [project, setProject] = useState(emptyProject);

  // Joiner being edited: { sectionId, anchorRect } | null.
  const [editingJoiner, setEditingJoiner] = useState(null);

  // What a newly added scene joins with. Adding a folder of sixteen
  // scenes used to produce fifteen hard cuts and leave the user to click
  // each boundary in turn — for a compilation, the transition is the
  // point, so the default is the fade and a cut is what you opt into.
  // Shown on the Build header rather than inferred, so the rule is
  // visible before the import rather than discovered after it.
  const [newSceneJoinerKind, setNewSceneJoinerKind] = useState('fade_through_black');
  // The settings each kind will be created with, kept PER KIND so
  // switching Fade → Title → Fade does not throw away the fade you set
  // up. A joiner kind is a family, not a single transition: a 5s hold
  // and a half-second dip are both "fade through black" and look
  // nothing alike, so the defaults are the user's to choose.
  const [joinerTemplates, setJoinerTemplates] = useState(() => {
    const t = {};
    for (const k of FA_DATA.JOINER_KINDS) t[k.kind] = makeJoinerFromKind(k.kind);
    return t;
  });
  // { anchorRect } while the template editor is open.
  const [editingNewJoiner, setEditingNewJoiner] = useState(null);
  const newSceneJoiner = joinerTemplates[newSceneJoinerKind]
    || makeJoinerFromKind(newSceneJoinerKind);

  // Picking a kind selects it, and opens its editor when it has anything
  // to set up — which is what makes this a template rather than a
  // fixed default.
  function pickNewSceneJoiner(kind, anchorRect) {
    setNewSceneJoinerKind(kind);
    const spec = FA_DATA.JOINER_KINDS.find(k => k.kind === kind);
    if ((spec?.params || []).length) setEditingNewJoiner({ anchorRect });
  }

  // The editor can change the KIND from inside itself, so store what
  // comes back under its own kind and follow it.
  function updateNewSceneJoiner(j) {
    if (!j?.kind) return;
    if (j.kind !== newSceneJoinerKind && joinerTemplates[j.kind]) {
      // The editor's own kind switcher hands back catalogue defaults.
      // Switching Fade → Title → Fade inside it would otherwise throw
      // away the fade the user just set up, while switching with the
      // header buttons kept it — the same gesture, two answers.
      setNewSceneJoinerKind(j.kind);
      return;
    }
    setJoinerTemplates(t => ({ ...t, [j.kind]: j }));
    setNewSceneJoinerKind(j.kind);
  }
  // Collapsed by default: it loads video, and most passes over the
  // canvas are about order and naming, not watching.
  const [previewOpen, setPreviewOpen] = useState(false);

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
  // Pressed, but the forge has not begun yet. See `startForge`.
  const [starting,      setStarting]      = useState(false);
  const [ioError,       setIoError]       = useState(null);
  // Which of the project's files are not on disk. Null until checked;
  // `{ entries, checked, summary }` after. Separate from `ioError`
  // because it is a STATE of the project, not an event -- it stays on
  // screen until it is fixed, where an error banner is dismissed and
  // forgotten.
  const [missingMedia,  setMissingMedia]  = useState(null);
  // Something worth saying that is NOT a failure -- cancelling a forge is
  // the first of them. Kept separate from `ioError` rather than given a
  // tone flag beside it: a flag has to be reset by every one of the dozen
  // `setIoError` call sites, and the one that forgets leaves a real error
  // wearing a reassuring colour.
  const [ioNotice,      setIoNotice]      = useState(null);
  // Batch .forge import progress: { done, total, name } | null. Importing
  // a folder of scenes extracts each bundle, which is not instant.
  const [batchImport,   setBatchImport]   = useState(null);

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
  function reorderSection(sectionId, anchorSectionId, position) {
    setProject(p => reorderSectionInProject(p, sectionId, anchorSectionId, position));
    markDirty();
  }

  // The compilation's title page, open in the joiner editor.
  const [editingTitlePage, setEditingTitlePage] = useState(null);
  function updateTitlePage(next) {
    setProject(p => ({ ...p, output: { ...p.output, openingJoiner: next } }));
    setDirty(true);
  }

  // { sectionId, title } while the removal is being confirmed.
  const [confirmRemove, setConfirmRemove] = useState(null);

  // Ask before throwing away a scene. This used to be a window.confirm
  // inside the button, which under Tauri returns a Promise -- so the
  // guard tested a truthy object, never fired, and the scene went
  // without a question being asked.
  function requestRemoveSection(sectionId) {
    const sec = project.sections.find(s => s.id === sectionId);
    if (!sec) return;
    // An empty row has nothing to lose; do not make a ceremony of it.
    if (!sec.segments.length) { handleRemoveSection(sectionId); return; }
    setConfirmRemove({
      sectionId,
      title: sec.title || sec.segments[0]?.title || 'this scene',
    });
  }

  // ── Remove a scene ─────────────────────────────────────────────
  // A scene IS a section, so removing one removes its section. Removing
  // the last scene leaves the empty boot state rather than refusing:
  // "keep at least one section" meant the final scene could not be
  // deleted, which read as a broken button.
  function handleRemoveSection(sectionId) {
    setProject(p => {
      const rest = p.sections.filter(s => s.id !== sectionId);
      if (rest.length) return { ...p, sections: rest };
      return {
        ...p,
        sections: [{ id: `sec-${Date.now()}`, title: '', color: '#ff8c42',
                     joiner: { kind: 'none' }, segments: [], overlays: [] }],
      };
    });
    markDirty();
    clearClipSelection();
  }

  // ── New (empty) project ────────────────────────────────────────
  // Clears the canvas to a single empty section — the starting point for
  // building a compilation from scratch (Add folder / Add .forge scene).
  function handleNewProject() {
    setMissingMedia(null);
    setProject(emptyProject());
    setSavedPath(null);
    setDirty(true);
    setLastSavedAtMs(null);
    clearClipSelection();
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
  // Pressing Save and getting nothing back reads as a broken button, and
  // it was: an unchanged project returned silently, and even a real save
  // only nudged a pill and a "saved just now" that already said that. Say
  // something every time, including when there was nothing to do.
  // The file being written right now, or null. Writing a project is not
  // instant on a big compilation, and until this existed the only feedback
  // was the Save As dialog sitting there looking like it had not taken the
  // click.
  const [saving, setSaving] = useState(null);
  const [saveFlash, setSaveFlash] = useState(null);
  const saveFlashTimer = useRef(null);
  function flashSaved(text) {
    setSaveFlash(text);
    if (saveFlashTimer.current) clearTimeout(saveFlashTimer.current);
    saveFlashTimer.current = setTimeout(() => setSaveFlash(null), 2600);
  }
  useEffect(() => () => {
    if (saveFlashTimer.current) clearTimeout(saveFlashTimer.current);
  }, []);

  function handleSaveClick() {
    if (!savedPath) { setIoDialog("save"); return; }
    if (!dirty) { flashSaved("No changes to save"); return; }
    saveInPlace();
  }
  async function saveInPlace() {
    if (!savedPath) { setIoDialog("save"); return; }
    setSaving(baseName(savedPath));
    try {
      await saveProject(savedPath, toForgeProject(project, { folder: project.output?.folder }));
      setDirty(false);
      setLastSavedAtMs(Date.now());
      // Save-in-place refreshes the recents entry too. Only Save-As did,
      // so a project that fell off the end of the list (or whose entry was
      // lost) never came back no matter how often you saved it.
      pushRecent(savedPath, project.name);
      flashSaved(`Saved ${baseName(savedPath)}`);
    } catch (e) {
      console.error('[save] failed', e);
      setIoError(`Couldn't save ${savedPath}: ${e?.message || e}`);
    } finally {
      setSaving(null);
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
    // Close the dialog on the way IN, not on the way out. It used to close
    // only after a successful write, so the whole wait happened behind a
    // dialog that gave no sign it had accepted the click -- and the obvious
    // move is to press Save again.
    setIoDialog(null);
    setSaving(baseName(path));
    try {
      await saveProject(path, toForgeProject(nextVm, { folder }));
      setProject(nextVm);
      setSavedPath(path);
      setDirty(false);
      setLastSavedAtMs(Date.now());
      pushRecent(path, nextVm.name);
      flashSaved(`Saved ${baseName(path)}`);
      // Where this project was saved is where the next one starts, and
      // its folder is where the forge writes.
      if (folder) rememberFolder('output', folder);
      // ...and it is where Open should look. Only the OUTPUT folder was
      // remembered here, so after saving a project and never opening
      // one, Open had no start directory and fell through to wherever
      // Windows last was — the folder the scenes were imported from.
      rememberFileFolder('projectOpen', path);
      // If we were saving en route to opening another project, continue.
      if (pendingAfterSave) { const a = pendingAfterSave; setPendingAfterSave(null); a(); }
    } catch (e) {
      console.error('[save] failed', e);
      setIoError(`Couldn't save ${path}: ${e?.message || e}`);
    } finally {
      setSaving(null);
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
  // A saved .forgeproject.json carries NO durations. The engine probes every
  // video itself at forge time, so nothing ever had a reason to write them
  // down — but the UI needs them, and only the *add* path was probing. The
  // result: every reopened project showed 0.0s on each scene and a total of
  // just the joiner holds ("0:03" for a 59-minute compilation), while the
  // forge quietly produced the correct file. Nothing was wrong with the
  // output; the canvas simply had no idea how long anything was.
  //
  // Probes are deduped in api/forge.js, so several scenes cut from one
  // source cost a single call. This is cached data, not an edit, so it
  // deliberately does not markDirty().
  // Scene rows showed a film icon instead of a frame. `extract_thumbnail`
  // has existed in the bridge the whole time and nothing ever called it,
  // so the only scenes with a picture were `.forge` imports, which carry
  // a hero still in the bundle — and even those lost it on reopen,
  // because the project file records no thumbnail path. Same shape of
  // hole as the missing durations.
  //
  // Frames are taken a second past the trim-in point: scenes commonly
  // open on black or a fade, and a black thumbnail is no more use than
  // the icon it replaced.
  //
  // Run one at a time, not Promise.all. Each is an ffmpeg process, and a
  // folder import is sixteen of them — see the 0xC0000142 note in
  // concat_audio_estim.py for what happens when this machine is asked
  // for too many processes at once.
  async function hydrateThumbs(vm) {
    const wanted = [];
    for (const sec of vm.sections || []) {
      for (const seg of sec.segments || []) {
        if (!seg.file || seg.thumb || seg.thumbPath) continue;
        if (seg.kind === 'still') continue;
        wanted.push(seg);
      }
    }
    if (!wanted.length) return;
    for (const seg of wanted) {
      const at = (seg.trimStartMs || 0) + 1000;
      try {
        const out = await thumbnailPathFor(seg.file, at);
        if (!out) return;                 // no filesystem (browser mock)
        const written = await extractThumbnail(seg.file, at, out);
        if (!written) continue;
        setProject(p => ({
          ...p,
          sections: p.sections.map(s => ({
            ...s,
            segments: s.segments.map(x => (
              x.id === seg.id && !x.thumb && !x.thumbPath
                ? { ...x, thumbPath: written }
                : x
            )),
          })),
        }));
      } catch (e) {
        // A missing codec or an unreadable file costs this one picture,
        // never the import.
        console.warn('[thumb] could not extract', seg.file, e);
      }
    }
  }

  // ── Missing media ─────────────────────────────────────────────────
  //
  // A project stores absolute paths, so two ordinary things break it: a
  // folder moves, or the same drive comes up as a different letter on
  // another machine. Before this, the only sign was a blank thumbnail --
  // which also means "not extracted yet", "codec unreadable" and "the
  // bundle is out of date", so it told you nothing.
  //
  // One batched `paths_exist` for the whole project: a stat each, no
  // ffprobe, no round trip per clip.
  async function checkMedia(vm) {
    const wanted = mediaPathsOf(vm);
    if (!wanted.length) { setMissingMedia(null); return null; }
    let flags;
    try {
      flags = await pathsExist(wanted.map((w) => w.path));
    } catch (e) {
      // Never let this cost someone the project they just opened.
      console.warn('[media] existence check failed', e);
      setMissingMedia(null);
      return null;
    }
    const entries = wanted.filter((_, i) => flags[i] === false);
    const state = entries.length
      ? { entries, checked: wanted.length,
          summary: describeMissing(entries, wanted.length) }
      : null;
    setMissingMedia(state);
    return state;
  }

  // Point the project at where the files went.
  //
  // By ROOT, not file by file. Whatever moved, moved together -- that is
  // what a folder is -- so the question to ask is "where is this folder
  // now", once, rather than the same question forty times.
  async function handleRelinkMedia() {
    if (!missingMedia?.entries?.length) return;
    setIoError(null);
    const oldRoot = commonRoot(missingMedia.entries.map((m) => m.path));
    if (!oldRoot) {
      setIoError('These files are in different places, so there is no single '
               + 'folder to re-point. Replace them one at a time from the clip editor.');
      return;
    }
    const picked = await pickFolder({ startDir: lastFolder('scenes') });
    if (!picked) return;

    const { mapping, unresolved } = planRemap(missingMedia.entries, oldRoot, picked);
    if (!mapping.size) {
      setIoError(`Nothing under ${oldRoot} could be re-pointed at ${picked}.`);
      return;
    }
    // CHECK before committing. A relink that cheerfully rewrites forty paths
    // onto forty files that are also not there is worse than one that fails.
    const candidates = [...mapping.values()];
    let flags;
    try {
      flags = await pathsExist(candidates);
    } catch (e) {
      setIoError(`Could not check ${picked}: ${e?.message || e}`);
      return;
    }
    const good = new Map();
    let i = 0;
    for (const [from, to] of mapping) {
      if (flags[i]) good.set(from, to);
      i += 1;
    }
    if (!good.size) {
      setIoError(`No missing file was found in ${picked}. `
               + 'Pick the folder that now holds them.');
      return;
    }

    const next = applyRemap(project, good);
    setProject(next);
    markDirty();
    rememberFolder('scenes', picked);
    const still = (missingMedia.entries.length - good.size);
    flashSaved(still
      ? `Relinked ${good.size} of ${missingMedia.entries.length} — ${still} still missing`
      : `Relinked ${good.size} file${good.size === 1 ? '' : 's'}`);
    // Re-check rather than subtract: the rewrite is the only thing that
    // decides what is found now, and trusting the arithmetic instead is how
    // a banner ends up disagreeing with the disk.
    checkMedia(next);
    hydrateThumbs(next).catch(() => {});
    void unresolved;
  }

  // Re-point ONE clip. The folder relink handles whatever moved together;
  // this is for the file that did something of its own -- in practice, got
  // renamed, which no amount of path arithmetic can follow.
  async function handleReplaceVideo(seg) {
    if (!seg?.id) return;
    setIoError(null);
    const picked = await pickFile({
      title: `Find the video for “${seg.title || baseName(seg.file)}”`,
      filterName: 'Video',
      extensions: ['mp4', 'mkv', 'mov', 'm4v', 'webm', 'avi', 'wmv'],
      startDir: parentFolder(seg.file) || lastFolder('scenes'),
    });
    if (!picked) return;

    const next = applyRemap(project, new Map([[seg.file, picked]]));
    setProject(next);
    markDirty();
    rememberFileFolder('scenes', picked);
    flashSaved(`Pointed at ${baseName(picked)}`);
    checkMedia(next);
    // The duration belongs to the NEW file, and the old one's is now a
    // guess about a file this clip no longer uses.
    hydrateDurations(next).catch(() => {});
    hydrateThumbs(next).catch(() => {});
  }

  async function hydrateDurations(vm) {
    const files = new Set();
    for (const sec of vm.sections || []) {
      for (const seg of sec.segments || []) {
        if (seg.file && !seg.durMs) files.add(seg.file);
      }
    }
    if (!files.size) return;
    const pairs = await Promise.all([...files].map(async (f) => {
      try { return [f, await probeDuration(f)]; } catch { return [f, 0]; }
    }));
    const byFile = new Map(pairs.filter(([, ms]) => ms > 0));
    if (!byFile.size) return;
    setProject(p => ({
      ...p,
      sections: p.sections.map(s => ({
        ...s,
        segments: s.segments.map(seg => (
          !seg.durMs && seg.file && byFile.has(seg.file)
            ? { ...seg, durMs: byFile.get(seg.file) }
            : seg
        )),
      })),
    }));
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
        rememberFileFolder('projectOpen', path);
        setTab('build');
        return;
      }
      const vm = fromForgeProject(json);
      setProject(vm);
      setSavedPath(path);
      setDirty(false);
      setLastSavedAtMs(Date.now());
      pushRecent(path, vm.name || name);
      rememberFileFolder('projectOpen', path);
      setTab('build');
      // Not awaited: the canvas should appear at once and fill in its
      // durations a moment later, exactly as it does after an import.
      hydrateDurations(vm).catch(e => console.warn('[open] duration probe failed', e));
      hydrateThumbs(vm).catch(e => console.warn('[open] thumbnails failed', e));
      // Checked on open, not at forge time. `validate()` has always
      // reported a missing video as a hard error, but only when Forge was
      // pressed -- so a project could look perfectly fine for an hour of
      // editing and then refuse at the end.
      checkMedia(vm).catch(e => console.warn('[open] media check failed', e));
    } catch (e) {
      console.error('[open] failed', e);
      setIoError(`Couldn't open ${path}: ${e?.message || e}`);
    }
  }


  // ── Add a FOLDER of .forge scenes — the header "Add folder…" ──
  // The standard: a `.forge` file is a finished SCENE, and a scene is a
  // SECTION (which is what becomes a chapter). So a folder of scenes
  // becomes a run of scenes in name order, ready for the user to set the
  // joiners between them. A `.forge` scene is the only thing this app
  // takes: loose videos and scattered funscripts are a later release.
  async function handleAddForgeFolder() {
    setIoError(null);
    const folder = await pickFolder({ startDir: lastFolder('scenes') });
    if (!folder) return;
    rememberFolder('scenes', folder);
    let payload;
    try {
      payload = await detectForgeFolder(folder);
    } catch (e) {
      console.error('[detect-forge] failed', e);
      setIoError(`Couldn't scan ${folder}: ${e?.message || e}`);
      return;
    }
    const bundles = payload?.bundles || [];
    if (!bundles.length) {
      // Say what this button looks for. Silence here reads as a bug, and
      // a folder of loose videos is the likeliest reason to find none.
      setIoError(`No .forge scenes in ${folder}. `
        + `ForgeAssembler joins finished .forge scenes — export one from `
        + `FunscriptForge, then add the folder it landed in.`);
      return;
    }

    setBatchImport({ done: 0, total: bundles.length, name: bundles[0].stem });
    const skipped = [];
    try {
      for (let i = 0; i < bundles.length; i++) {
        const b = bundles[i];
        setBatchImport({ done: i, total: bundles.length, name: b.stem });
        // `false` = don't prompt for a missing video. Ten dialogs in a row
        // is not a workflow; collect the unresolved ones and say so once.
        const ok = await importForgeScene(b.path, { prompt: false });
        if (!ok) skipped.push(b.stem);
      }
    } finally {
      setBatchImport(null);
    }
    if (skipped.length) {
      setIoError(`Added ${bundles.length - skipped.length} of ${bundles.length} scenes. `
        + `Couldn't resolve the source video for: ${skipped.join(', ')}. `
        + `Add those with "Add .forge scene…" to pick each video.`);
    }
  }


  // Import a `.forge` bundle as a new scene: explicit channel map, with a
  // relink prompt when the lean bundle carries no media. Shared by the
  // "Add .forge scene…" and "Add folder…" header buttons.
  // `prompt: false` (batch import) never opens a relink dialog — it
  // returns false so the caller can collect the unresolved scenes and
  // report them once, instead of firing one modal per bundle.
  // Import a `.forge` and hand back a segment, or null. Split out of
  // `importForgeScene` because branding needs the same import -- including
  // the relink prompt when a lean bundle carries no media -- but puts the
  // result somewhere other than a new section.
  async function forgeBundleToSegment(bundle, { prompt = true } = {}) {
    let payload;
    try {
      payload = await importForgeBundle(bundle);
    } catch (e) {
      console.error('[import-forge] failed', e);
      if (prompt) setIoError(`Couldn't import ${bundle}: ${e?.message || e}`);
      return null;
    }
    if (payload?.needs_video) {
      if (!prompt) return null;
      const video = await pickFile({
        title: `Select the source VIDEO for “${payload.stem || 'this scene'}”`,
        filterName: 'Video', extensions: ['mp4', 'mov', 'mkv', 'webm', 'm4v', 'avi'],
        startDir: lastFolder('scenes'),
      });
      if (!video) {
        setIoError(`Import canceled — “${payload.stem || 'scene'}” needs a source video to relink.`);
        return null;
      }
      try {
        payload = await importForgeBundle(bundle, { video });
      } catch (e) {
        console.error('[import-forge] relink failed', e);
        setIoError(`Couldn't relink video: ${e?.message || e}`);
        return null;
      }
    }
    const seg = fromForgeBundleSegment(payload?.segment, payload);
    if (!seg) {
      if (prompt) setIoError(`Import produced no segment for ${payload?.stem || bundle}.`);
      return null;
    }
    seg.id = `${seg.id || 'seg'}-${Date.now()}`;
    return seg;
  }

  async function importForgeScene(bundle, { prompt = true } = {}) {
    const seg = await forgeBundleToSegment(bundle, { prompt });
    if (!seg) return false;
    // One scene, one section, always. A SECTION is what becomes a chapter,
    // so dropping two scenes into one section gave a two-scene compilation a
    // single chapter marker at 0:00 — nothing to navigate to. Nothing can put
    // a second clip in a section any more, and that is what makes the Build
    // canvas a flat list of scenes rather than a tree.
    appendSceneAsSection(seg);
    return true;
  }

  // Append a new section holding `segs`, named after the first one — so
  // the chapter title is the scene's name without the user renaming
  // anything. Reuses a trailing EMPTY section (the boot state has one)
  // instead of leaving a blank chapter in front of the first scene.
  // A title card with nothing written on it is a blank three seconds the
  // engine refuses to forge. Adding a folder of sixteen scenes with the
  // picker on Title must not produce sixteen of those, so the card is
  // born naming the scene it introduces — which is also the chapter
  // name. Renaming it afterwards is a normal edit.
  function makeSceneJoiner(kind, seg) {
    const j = { ...(joinerTemplates[kind] || makeJoinerFromKind(kind)) };
    // A title left blank in the template means "name each scene". Typing
    // one there instead makes every card say the same thing, which is a
    // reasonable thing to want and has to stay possible.
    //
    // `titleForClip` rather than the section title: the section is labelled
    // with the raw stem, which is right for a row in a list and wrong on a
    // card -- `-madmartigan----its-just-ai-sex` is not a title. A bookmark
    // comes through untouched, because that is a name a person chose.
    if (j.kind === 'title_card' && !j.title) j.title = titleForClip(seg) || '';
    return j;
  }

  function appendSceneAsSection(seg) {
    if (!seg) return;
    markDirty();
    const title = seg.title || '';
    setProject(p => {
      const last = p.sections[p.sections.length - 1];
      // A section's leading joiner is the transition INTO it, so the
      // first scene never gets one — there is nothing before it to
      // transition from.
      const isFirst = (i) => i === 0;
      if (last && last.segments.length === 0) {
        const i = p.sections.length - 1;
        return {
          ...p,
          sections: p.sections.map((s, idx) => idx === i
            ? {
                ...s,
                title: s.title || title,
                segments: [seg],
                // Reusing the empty boot section: it only needs a joiner
                // if something already plays before it.
                joiner: isFirst(idx) ? { kind: 'none' }
                                     : makeSceneJoiner(newSceneJoinerKind, seg),
              }
            : s),
        };
      }
      return {
        ...p,
        sections: [...p.sections, {
          id: `sec-${Date.now()}`, title, color: '#ff8c42',
          joiner: makeSceneJoiner(newSceneJoinerKind, seg),
          segments: [seg], overlays: [],
        }],
      };
    });
    // A `.forge` import already carries its bundle's hero still; anything
    // else gets a frame pulled from the video.
    if (seg.file && !seg.thumb && !seg.thumbPath && seg.kind !== 'still') {
      hydrateThumbs({ sections: [{ segments: [seg] }] })
        .catch(e => console.warn('[add] thumbnail failed', e));
    }
    if (seg.file && !seg.durMs) {
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

  // ── Add a finished FunscriptForge `.forge` scene (header button) ──
  // ── Branding: an optional `.forge` at each end of the compilation ──
  //
  // A bumper is a scene like any other -- it brings its own audio AND its own
  // funscripts, which is what makes the intro usable to calibrate a device
  // before any content plays. It belongs to no section, so it gets no chapter
  // marker: chapter 01 stays the first real scene.
  async function handlePickBranding(which) {
    setIoError(null);
    const bundle = await pickFile({
      title: which === 'intro'
        ? 'Select a .forge scene to play BEFORE the compilation'
        : 'Select a .forge scene to play AFTER the compilation',
      filterName: 'FunscriptForge bundle', extensions: ['forge'],
      startDir: rememberedBranding(which) || lastFolder('branding') || lastFolder('scenes'),
    });
    if (!bundle) return;
    const seg = await forgeBundleToSegment(bundle);
    if (!seg) return;
    rememberFileFolder('branding', bundle);
    // Remembered so the NEXT compilation offers it: a studio bumper does not
    // change per release. What the project saves is the segment above.
    rememberBranding(which, bundle);
    setBranding(which, seg);
  }

  function setBranding(which, seg) {
    const key = which === 'intro' ? 'brandingIntro' : 'brandingOutro';
    setProject(p => ({ ...p, output: { ...p.output, [key]: seg } }));
    markDirty();
  }

  // ── Branding as a reusable PRESET ─────────────────────────────────
  //
  // The title page, the bumper at each end and the overlays over them are the
  // one part of a compilation that is the same every time. Rebuilding them by
  // hand per project is how one release's credits end up saying something
  // slightly different from the last one's.
  async function handleSaveBranding() {
    setIoError(null);
    if (!hasBranding(project)) {
      setIoError('There is no branding in this project to save yet.');
      return;
    }
    const path = await pickSavePath(brandingFileName(project.name), {
      filters: BRANDING_FILTERS,
      startDir: lastFolder('branding') || lastFolder('projectOpen'),
    });
    if (!path) return;
    try {
      await writeJsonFile(path, extractBranding(project, {
        name: projectDisplayName(path),
      }));
      rememberFileFolder('branding', path);
      flashSaved('Branding saved');
    } catch (e) {
      setIoError(`Could not save the branding: ${e?.message || e}`);
    }
  }

  async function handleLoadBranding() {
    setIoError(null);
    const path = await pickFile({
      title: 'Load branding into this project',
      filters: BRANDING_FILTERS,
      startDir: lastFolder('branding') || lastFolder('projectOpen'),
    });
    if (!path) return;
    let doc;
    try {
      doc = await readJsonFile(path);
    } catch (e) {
      setIoError(`Could not read that file: ${e?.message || e}`);
      return;
    }
    if (!isBrandingDoc(doc)) {
      // Named, because "invalid file" leaves someone staring at a picker
      // wondering which of four similar files they grabbed.
      setIoError(`${projectDisplayName(path)} is not a branding file.`);
      return;
    }
    rememberFileFolder('branding', path);
    // REPLACES this project's branding -- see `applyBranding`. Everything
    // else, including the sections, is untouched.
    setProject(p => applyBranding(p, doc));
    markDirty();
    flashSaved(`Branding loaded · ${describeBranding(doc)}`);
  }

  // Overlays over the whole compilation. One list, replaced wholesale --
  // the dialog hands back the finished array, so there is no add/edit/remove
  // branching here to drift out of step with it.
  function setOverlays(list) {
    setProject(p => ({ ...p, output: { ...p.output, overlays: list } }));
    markDirty();
  }

  async function handleAddForgeScene() {
    setIoError(null);
    const bundle = await pickFile({
      title: 'Select a .forge scene to import',
      filterName: 'FunscriptForge bundle', extensions: ['forge'],
      startDir: lastFolder('scenes'),
    });
    if (!bundle) return;
    rememberFileFolder('scenes', bundle);
    await importForgeScene(bundle);
  }

  // Drop a selection that the loaded/edited project no longer contains.
  useEffect(() => {
    const ids = project.sections.flatMap(s => s.segments).map(s => s.id);
    setSelectedIds(prev => {
      const kept = prev.filter(id => ids.includes(id));
      return kept.length === prev.length ? prev : kept;
    });
  }, [project]);

  // Normalised once per check rather than per row: the canvas re-renders
  // on every selection change, and this is read for every clip on it.
  const missingPaths = useMemo(() => new Set(
    (missingMedia?.entries || []).map(
      (m) => String(m.path).replace(/\\/g, '/').toLowerCase()),
  ), [missingMedia]);

  const flatSegments = project.sections.flatMap(s => s.segments);
  const sceneCount = project.sections.filter(s => s.segments.length).length;
  const totalMs = projectDurationMs(project, FA_DATA.joinerAddedMs);

  // Whether "Mark forged" may be pressed. Memoized on the project because
  // this stringifies it, and App re-renders on every ffmpeg progress tick
  // during a forge.
  const sig = useMemo(() => projectSignature(project), [project]);
  const markForged = markForgedGate({ forging, sig, forgedSig });
  const selectedSegs = flatSegments.filter(s => selectedIds.includes(s.id));

  function selectClip(id) { setSelectedIds([id]); }
  function clearClipSelection() { setSelectedIds([]); }

  // Update whichever scene is selected. Duplicate and bulk-remove went
  // with the multi-select model: both existed to act on several clips
  // inside one section, and a section holds exactly one scene now.
  function updateSelected(partial) {
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

  // The pipeline order the tab strip enforces (FA_TABS in AppShell): each
  // tab unlocks the next. The button says "Accept and chain" — it has to
  // actually chain, which it never did; it only set the flag and left you
  // on the same tab wondering why nothing happened. Re-accept advances
  // too, since that's the same gesture on an already-accepted step.
  const TAB_CHAIN = ["build", "output", "forge"];

  const accept = (key) => {
    setPipeline(p => ({ ...p, [key]: { ...p[key], accepted: true } }));
    const next = TAB_CHAIN[TAB_CHAIN.indexOf(key) + 1];
    if (next) setTab(next);
  };
  // Un-accepting a step invalidates everything downstream of it — an
  // Output that was accepted against a different Build isn't accepted.
  const reset = (key) => setPipeline(p => {
    const from = TAB_CHAIN.indexOf(key);
    const next = { ...p };
    for (const k of TAB_CHAIN.slice(from < 0 ? 0 : from)) {
      if (next[k]) next[k] = { ...next[k], accepted: false };
    }
    return next;
  });

  // Real forge: ensure the project is saved to disk, subscribe to the
  // `fa:progress` stream, run `forge`, then reveal the output.
  // ⚠ A ref, not the `forging` state.
  //
  // The guard below used to read `forging`, and `setForging(true)` is
  // eleven lines and two awaits further down — so a second click during
  // the pre-save or the validation walked straight past it, and React
  // would not have updated the state within one tick anyway. Measured on
  // a real double-click: two CLI children a second apart, both ffmpegs
  // writing `-y` to the SAME output path. Two writers on one file is how
  // you get an unplayable render.
  //
  // A ref changes synchronously, so the second click sees it.
  const forgingRef = useRef(false);
  // True from the moment Cancel is clicked until the run actually ends, so
  // the button can stop the user clicking it a second time while the tree
  // is being killed -- which takes a moment on a 4K encode.
  const [cancelling, setCancelling] = useState(false);

  async function startForge() {
    if (forgingRef.current) return;
    forgingRef.current = true;
    // `forging` does not go true until `runForge` has saved the project,
    // validated it through the CLI and probed the first clip -- easily most
    // of a second, during which the button still said "Forge" and still
    // looked pressable. The ref above already made a second press harmless;
    // this makes it look harmless, which is the part the user sees.
    setStarting(true);
    try {
      await runForge();
    } finally {
      forgingRef.current = false;
      setStarting(false);
      setCancelling(false);
    }
  }

  async function runForge() {
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
      (project.channels?.audio_estim ? 1 : 0) +
      (project.output?.forgeBundle !== false ? 1 : 0));
    // Stage identity, not a count — see makeStageTracker. Two forges
    // sharing the `fa:progress` channel used to drive this to the end of
    // the list in the first second.
    const stages = makeStageTracker();
    let stage = 0;          // 1-based index of the stage in flight
    let durationMs = 0;     // output length, from the CLI's `meta:` line
    let shown = 0;          // last value pushed — the bar never walks back
    // Each stage's share of the bar, in stage order, from the CLI. Equal
    // slices were badly wrong: the video encode is the overwhelming
    // majority of the wall clock but was worth only 1/4 of the bar, so a
    // 4K render sat at "22%" while nearly finished. Null until `meta:`
    // arrives, and for an older CLI that never sends it — equal slices
    // then, which is the old behaviour rather than a broken one.
    let weights = null;
    const advance = (frac) => {
      const v = stageProgress({ stage, stageCount, weights, frac });
      if (v > shown) { shown = v; setProgress(v); }
    };

    setIoError(null);
    // Clear last run's "cancelled" so it cannot hang over this one.
    setIoNotice(null);
    // The project as the engine is about to see it, captured before the
    // render starts. Editing the canvas while ffmpeg runs must not leave a
    // finished file looking current.
    const renderedSig = sig;
    setForging(true); setProgress(0); setForgeStage('Starting…');
    let unlisten = () => {};
    try {
      unlisten = await onForgeProgress((line) => {
        const ev = parseProgressLine(line);
        if (!ev) return;
        if (ev.kind === 'meta') {
          if (ev.durationMs) durationMs = ev.durationMs;
          if (ev.stages) stageCount = Math.max(1, ev.stages);
          if (ev.weights) weights = ev.weights;
          return;
        }
        if (ev.kind === 'stage') {
          stage = Math.min(stageCount, stages.saw(ev.text));
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
      // Record WHAT was rendered, not merely that a render happened.
      setForgedSig(renderedSig);
      accept('forge');
      if (summary?.video) setForgedPath(summary.video);
      const reveal = summary?.video || project.output?.folder;
      if (reveal) revealPath(reveal).catch(() => {});
    } catch (e) {
      // A cancel is not a failure. The Rust side kills the child, which
      // exits non-zero exactly as a crash would, so this sentinel is the
      // only thing that tells them apart -- without it the user gets
      // "Forge failed" for something they chose to do.
      if (String(e?.message || e).includes(FORGE_CANCELLED)) {
        console.info('[forge] cancelled by the user');
        setForgeStage(null);
        setProgress(null);
        // Said plainly, because the reassuring half is not obvious: the
        // encode went to a temp file, so the render it would have replaced
        // is still there. A NOTICE, not an error -- it would be a strange
        // thing to say inside a red box.
        setIoNotice('Forge cancelled. Nothing was written — any earlier '
                    + 'render in the output folder is untouched.');
      } else {
        console.error('[forge] failed', e);
        setIoError(`Forge failed: ${e?.message || e}`);
        setForgeStage(null);
      }
    } finally {
      unlisten();
      setForging(false);
    }
  }

  // Stop the forge in flight. The engine publishes the video with
  // os.replace, so a killed encode loses only its temp.
  async function handleCancelForge() {
    if (!forgingRef.current || cancelling) return;
    setCancelling(true);
    setForgeStage('Cancelling…');
    try {
      await cancelForge();
    } catch (e) {
      console.error('[forge] cancel failed', e);
      setIoError(`Couldn't cancel the forge: ${e?.message || e}`);
      setCancelling(false);
    }
  }

  // ─── Tab body ──────────────────────────────────────────────────
  let body, acceptKey = null, acceptSummary = "", acceptLabel = "Accept and chain";
  let acceptDisabled = false, acceptDisabledReason = null;
  // When set, replaces the accept button entirely -- see FAAcceptBar.
  let acceptPrimary = null;

  if (tab === "home") {
    body = (
      <HomeScreen
        recents={recents}
        hasWork={flatSegments.length > 0}
        projectName={project.name}
        sceneCount={sceneCount}
        totalLabel={fmtTotal(totalMs)}
        onNew={handleNewProject}
        onOpen={handleOpenClick}
        onOpenRecent={openRecent}
        onContinue={() => setTab('build')} />
    );
  } else if (tab === "build") {
    acceptKey = "build";
    acceptSummary = `${sceneCount} scene${sceneCount === 1 ? "" : "s"} · ${sceneCount} chapter${sceneCount === 1 ? "" : "s"} · ${fmtTotal(totalMs)} total.`;
    body = (
      <div style={{ flex: 1, minHeight: 0, display: "flex" }}>
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
          <FATabBody>
            <DragDropProvider onReorderSection={reorderSection}>
              <BuildTab
                project={project}
                missingPaths={missingPaths}
                selectedIds={selectedIds}
                onSelect={selectClip}
                onEditJoiner={(sectionId, anchorRect) => setEditingJoiner({ sectionId, anchorRect })}
                onEditTitlePage={(anchorRect) => setEditingTitlePage({ anchorRect })}
                onRenameSection={renameSection}
                onAddForgeFolder={handleAddForgeFolder}
                newSceneJoinerKind={newSceneJoinerKind}
                newSceneJoiner={newSceneJoiner}
                onPickNewSceneJoiner={pickNewSceneJoiner}
                onEditNewSceneJoiner={(anchorRect) => setEditingNewJoiner({ anchorRect })}
                onAddForgeScene={handleAddForgeScene}
                onRemoveSection={requestRemoveSection}
                onEditClip={(seg) => setEditingClip(seg)} />
            </DragDropProvider>
          </FATabBody>
          <CompilationPreview project={project} open={previewOpen}
                               onToggle={() => setPreviewOpen(o => !o)} />
          <PreviewBand project={project} totalMs={totalMs} segCount={flatSegments.length} />
        </div>
        <Inspector
          segs={selectedSegs} project={project}
          onClose={clearClipSelection}
          onUpdate={updateSelected} />
      </div>
    );
  } else if (tab === "output") {
    body = <OutputTab project={project}
                       onSetOutput={setOutput}
                       onSetChannels={setChannels}
                       onPickBranding={handlePickBranding}
                       onClearBranding={(which) => setBranding(which, null)}
                       onSaveBranding={handleSaveBranding}
                       onLoadBranding={handleLoadBranding}
                       hasBranding={hasBranding(project)}
                       onSetOverlays={setOverlays} />;
    acceptKey = "output";
    acceptSummary = `Resolution ${project.output.resolution} · loudness ${project.output.normalizeAudio ? "−16 LUFS" : "off"}.`;
  } else if (tab === "viewer") {
    // No accept bar: the Viewer changes nothing, so there is nothing to chain.
    body = <ViewerTab project={project} forgedPath={forgedPath} />;
  } else if (tab === "forge") {
    body = <ForgeTab project={project} totalMs={totalMs} onForge={startForge}
                     onCancelForge={handleCancelForge} cancelling={cancelling}
                     forging={forging} starting={starting}
                     progress={progress} forgeStage={forgeStage} />;
    acceptKey = "forge";
    acceptSummary = forging ? "Forging in progress…" : (pipeline.forge.accepted ? "Forged successfully." : "Press Forge to render the combined output.");
    // This bar is not really an accept bar. It is where the long expensive
    // thing starts, and then where you go next once it has finished --
    // "Mark forged" asked the user to assert something the app already knew.
    // The card's own Forge button stays: this bar is always on screen, and
    // the card scrolls away.
    acceptPrimary = (forging || starting)
      ? { label: forging ? "Forging…" : "Starting…", icon: "hammer",
          kind: "secondary", disabled: true, reason: null, onClick: () => {} }
      : markForged.enabled
        ? { label: "Chain to Viewer", icon: "arrow-right", kind: "white",
            onClick: () => setTab("viewer") }
        : { label: "Forge", icon: "hammer", kind: "white", onClick: startForge };
  }

  // ─── Render ─────────────────────────────────────────────────────
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", background: "var(--bg)" }}>
      <FATopBar project={project} totalMs={totalMs}
                 sceneCount={sceneCount}
                 savedPath={savedPath} dirty={dirty} lastSavedAtMs={lastSavedAtMs}
                 saveFlash={saveFlash}
                 onOpen={handleOpenClick} onSave={handleSaveClick} onNew={handleNewProject}
                 onHome={goHome} />
      <FATabStrip active={tab} onChange={setTab} pipeline={pipeline} />

      {/* Missing media. Persistent, not dismissible: it describes the state
          of the project, and it goes away when the files are found. */}
      {missingMedia?.summary && (
        <div style={{
          display: "flex", alignItems: "center", gap: 12, flexShrink: 0,
          padding: "9px 18px",
          background: "rgba(255,181,71,0.08)",
          borderBottom: "1px solid rgba(255,181,71,0.35)",
          fontSize: 12.5, color: "var(--text)",
        }}>
          <Icon name="unlink" size={15} style={{ color: "var(--warn)", flexShrink: 0 }} />
          <div style={{ flex: 1, minWidth: 0, lineHeight: 1.45 }}>
            <span style={{ fontWeight: 600 }}>{missingMedia.summary.title}</span>{" "}
            <span style={{ color: "var(--text-muted)" }}>
              {missingMedia.summary.detail}
            </span>
          </div>
          <Button kind="primary" size="sm" icon="folder-search"
                  onClick={handleRelinkMedia}
                  title={missingMedia.summary.root
                    ? `Say where ${missingMedia.summary.root} is now`
                    : "Find the files"}>
            Find missing media…
          </Button>
        </div>
      )}

      <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
        {tab === "build" ? body : <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>{body}</div>}
      </div>

      {acceptKey && (
        <FAAcceptBar
          summary={acceptSummary}
          chainFile={pipeline[acceptKey].chainFile}
          accepted={pipeline[acceptKey].accepted}
          primaryLabel={acceptLabel}
          primary={acceptPrimary}
          disabled={acceptDisabled}
          disabledReason={acceptDisabledReason}
          onAccept={() => accept(acceptKey)}
          onReset={() => reset(acceptKey)} />
      )}
      <FAStatusBar activeTab={tab}
                    chainFile={acceptKey ? pipeline[acceptKey].chainFile : null}
                    saving={saving} dirty={dirty} savedPath={savedPath} />

      {/* ── Joiner editor overlay ── */}
      {/* The compilation's own title page — the same editor, with no
          scene either side of it, because there is none. */}
      {editingTitlePage && (
        <JoinerEditor
          joiner={project.output?.openingJoiner || { kind: 'none' }}
          prevClip={null}
          nextClip={project.sections?.[0]?.segments?.[0] || null}
          anchorRect={editingTitlePage.anchorRect}
          /* The compilation is named after the folder it lives in, which is
             usually the release name — a far better title than any one
             scene's filename. */
          defaultTitle={titleForFolder(
            project.output?.folder || parentFolder(savedPath) || '')}
          onChange={updateTitlePage}
          onClose={() => setEditingTitlePage(null)} />
      )}

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
            prevClip={prevClip}
            nextClip={nextClip}
            anchorRect={editingJoiner.anchorRect}
            /* The card introduces what comes NEXT, so it is named after the
               following scene, not the one fading out behind it. */
            defaultTitle={titleForClip(nextClip)}
            onChange={(newJ) => updateSectionJoiner(sec.id, newJ)}
            onClose={() => setEditingJoiner(null)} />
        );
      })()}
      {/* ── New-scene joiner template ── */}
      {editingNewJoiner && (() => {
        // Show it against the last two scenes so the preview is of the
        // user's own footage rather than placeholder panels.
        const scenes = project.sections.filter(s => s.segments.length);
        const lastSeg = scenes.length
          ? scenes[scenes.length - 1].segments[scenes[scenes.length - 1].segments.length - 1]
          : null;
        return (
          <JoinerEditor
            joiner={newSceneJoiner}
            prevClip={lastSeg}
            nextClip={null}
            anchorRect={editingNewJoiner.anchorRect}
            onChange={updateNewSceneJoiner}
            onClose={() => setEditingNewJoiner(null)} />
        );
      })()}

      {/* ── Confirm removing a scene ── */}
      {confirmRemove && (
        <Modal onClose={() => setConfirmRemove(null)} width={440}
                title="Remove this scene?"
                icon="trash-2"
                iconTone="warn"
                subtitle={
                  <span className="mono" style={{ color: "var(--text)" }}>
                    {confirmRemove.title}
                  </span>
                }>
          <div style={{ fontSize: 12.5, color: "var(--text-muted)", lineHeight: 1.5 }}>
            The scene leaves the compilation, along with its chapter and the
            transition into it. Your <span className="mono">.forge</span> file
            on disk is untouched, so you can add it back.
          </div>
          <ModalFooter>
            <Button kind="ghost" size="sm"
                     onClick={() => setConfirmRemove(null)}>Cancel</Button>
            <Button kind="danger" size="sm" icon="trash-2"
                     onClick={() => {
                       handleRemoveSection(confirmRemove.sectionId);
                       setConfirmRemove(null);
                     }}>Remove scene</Button>
          </ModalFooter>
        </Modal>
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
      {/* Batch .forge import — each bundle is extracted, so a folder of
          nine scenes is seconds of work with nothing on screen otherwise. */}
      {batchImport && (
        <div style={{
          position: "fixed", bottom: 56, left: "50%", transform: "translateX(-50%)",
          zIndex: 60, minWidth: 360, maxWidth: 560,
          padding: "10px 14px", borderRadius: 8,
          background: "var(--surface)", border: "1px solid var(--accent)",
          boxShadow: "var(--elev-3)", color: "var(--text)", fontSize: 12.5,
        }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
            <span style={{ flex: 1 }}>
              Importing scene {Math.min(batchImport.done + 1, batchImport.total)} of {batchImport.total}
            </span>
            <span className="mono" style={{ fontSize: 10.5, color: "var(--text-dim)",
                                             overflow: "hidden", textOverflow: "ellipsis",
                                             whiteSpace: "nowrap", maxWidth: 260 }}>
              {batchImport.name}
            </span>
          </div>
          <div style={{ height: 4, marginTop: 8, borderRadius: 2,
                         background: "var(--surface-2)", overflow: "hidden" }}>
            <span style={{ display: "block", height: "100%",
                            width: `${(batchImport.done / batchImport.total) * 100}%`,
                            background: "var(--accent)", transition: "width 120ms" }} />
          </div>
        </div>
      )}

      {/* One banner, two tones. A red border on "Forge cancelled" reads as
          "something went wrong" and flatly contradicts the words inside it. */}
      {(ioError || ioNotice) && !batchImport && (
        <div style={{
          position: "fixed", bottom: 56, left: "50%", transform: "translateX(-50%)",
          zIndex: 60, maxWidth: 560,
          display: "flex", alignItems: "center", gap: 10,
          padding: "10px 14px", borderRadius: 8,
          background: "var(--surface)",
          border: `1px solid ${ioError ? "var(--danger)" : "var(--border)"}`,
          boxShadow: "var(--elev-3)", color: "var(--text)", fontSize: 12.5,
        }}>
          <span style={{ flex: 1 }}>{ioError || ioNotice}</span>
          {/* Was `--text-dim` on transparent with no border, which is this
              app's disabled look — it read as greyed out while being fully
              clickable. A control that works must look like one. */}
          <button onClick={() => { setIoError(null); setIoNotice(null); }}
                  style={{ background: "transparent",
                           border: "1px solid var(--border)", borderRadius: 6,
                           padding: "4px 10px", color: "var(--text)",
                           cursor: "pointer", fontFamily: "inherit",
                           fontSize: 12, fontWeight: 600, flexShrink: 0 }}>
            Dismiss
          </button>
        </div>
      )}

      {/* Clip editor (trim · audio · remove) */}
      {editingClip && (
        <ClipEditor
          seg={editingClip}
          onSave={updateSegment}
          onRemove={removeSegment}
          onReplaceVideo={handleReplaceVideo}
          missing={missingPaths.has(
            String(editingClip.file || '').replace(/\\/g, '/').toLowerCase())}
          onClose={() => setEditingClip(null)} />
      )}

    </div>
  );
}

export { App };
