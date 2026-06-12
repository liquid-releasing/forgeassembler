/* @esm-converted */
import React from 'react';
import { FASectionLabel } from './AppShell';
import { Section } from './TitleEditor';
import { Button, Field, Icon, TextInput } from './primitives';

// ProjectIO — Save / Open / Unsaved-changes dialogs.
//
// In the real native app these wrap OS dialogs (NSOpenPanel, GTK file
// chooser, etc.). Here they're proxied to clear, dark-themed modals
// that demonstrate the flow.
//
// Three modals:
//   • <SaveAsDialog>      — first save (or Save As). Pick basename + folder.
//   • <OpenProjectDialog> — browse for file OR pick from recents.
//   • <UnsavedChangesDialog> — confirm before discarding edits.

const { useState: ioState, useEffect: ioUseEffect, useRef: ioRef } = React;

// ── A few mock recents shown in OpenProjectDialog ────────────────
const PIO_RECENTS = [
  { path: "C:/Users/bruce/Videos/forgeassembler/vol_03_compilation.forgeproject.json",
    name: "vol_03_compilation", when: "today · 14:22", segs: 8, dur: "8:46", res: "1080p" },
  { path: "C:/Users/bruce/Videos/forgeassembler/longform_session_aug.forgeproject.json",
    name: "longform_session_aug", when: "yesterday · 23:51", segs: 14, dur: "20:52", res: "1440p" },
  { path: "C:/Users/bruce/Videos/forgeassembler/lqr_marketing.forgeproject.json",
    name: "lqr_marketing", when: "Aug 12 · 19:00", segs: 4, dur: "0:48", res: "1080p" },
  { path: "C:/Users/bruce/Videos/forgeassembler/draft_test.forgeproject.json",
    name: "draft_test", when: "Aug 11 · 09:42", segs: 6, dur: "5:11", res: "1080p" },
];

// ── Save As dialog ───────────────────────────────────────────────
function SaveAsDialog({ project, defaultFolder, onCancel, onSave }) {
  const [basename, setBasename] = ioState(project.name || "untitled");
  const [folder, setFolder]     = ioState(defaultFolder || "C:/Users/bruce/Videos/forgeassembler");
  const filename = `${slug(basename)}.forgeproject.json`;
  const valid = basename.trim().length > 0 && folder.trim().length > 0;

  return (
    <Modal onClose={onCancel} width={520}
            title="Save project as…"
            icon="save"
            subtitle="Writes the project sidecar JSON. Forging writes the rest of the bundle alongside.">
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <Field label="File name"
                hint={`Saves to ${filename}`}>
          <TextInput value={basename} onChange={setBasename}
                      placeholder="my_project" />
        </Field>
        <Field label="Folder">
          <div style={{ display: "flex", gap: 6 }}>
            <TextInput value={folder} onChange={setFolder} mono style={{ flex: 1 }} />
            <Button kind="secondary" size="sm" icon="folder-open">Browse…</Button>
          </div>
        </Field>

        <div style={{ padding: "10px 12px", background: "var(--surface-2)",
                       border: "1px solid var(--border)", borderRadius: 6,
                       fontSize: 11.5, color: "var(--text-muted)", lineHeight: 1.5 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
            <Icon name="info" size={12} style={{ color: "var(--text-dim)" }} />
            <strong style={{ color: "var(--text-muted)" }}>What gets written now</strong>
          </div>
          <div className="mono" style={{ color: "var(--text)" }}>{folder}/{filename}</div>
          <div style={{ marginTop: 6 }}>
            The project file is a small JSON sidecar describing the section list, joiners,
            audio beds, and channel decisions. Video / funscript output files are written
            later when you press <strong style={{ color: "var(--text)" }}>Forge</strong>.
          </div>
        </div>
      </div>

      <ModalFooter>
        <Button kind="ghost" size="sm" onClick={onCancel}>Cancel</Button>
        <Button kind="primary" size="sm" icon="save" disabled={!valid}
                onClick={() => onSave({ path: `${folder}/${filename}`, basename: basename.trim(), folder })}>
          Save
        </Button>
      </ModalFooter>
    </Modal>
  );
}

// ── Open Project dialog ──────────────────────────────────────────
function OpenProjectDialog({ onCancel, onOpen }) {
  return (
    <Modal onClose={onCancel} width={580}
            title="Open project"
            icon="folder-open"
            subtitle="Pick a .forgeproject.json from disk, or click any recent below.">
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {/* Browse from disk */}
        <div style={{
          padding: 14, background: "var(--surface-2)",
          border: "1px solid var(--border)", borderRadius: 8,
          display: "flex", alignItems: "center", gap: 12,
        }}>
          <Icon name="file-json-2" size={20} style={{ color: "var(--text-dim)" }} />
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 600 }}>Browse for a file…</div>
            <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 2 }}>
              Opens your OS file picker. Only <span className="mono">.forgeproject.json</span> files are shown.
            </div>
          </div>
          <Button kind="primary" size="sm" icon="folder-open"
                   onClick={() => onOpen({ path: "C:/Users/bruce/Videos/forgeassembler/picked-file.forgeproject.json",
                                            name: "picked-file" })}>
            Browse…
          </Button>
        </div>

        {/* Recents */}
        <div>
          <FASectionLabel right={<Button kind="ghost" size="sm">Clear list</Button>}>
            Recent projects
          </FASectionLabel>
          <div style={{ display: "flex", flexDirection: "column", gap: 4,
                          maxHeight: 280, overflow: "auto" }}>
            {PIO_RECENTS.map((r) => (
              <button key={r.path}
                       onClick={() => onOpen({ path: r.path, name: r.name })}
                       style={{
                         display: "flex", alignItems: "center", gap: 12,
                         padding: "8px 10px", border: "1px solid var(--border)",
                         background: "transparent", borderRadius: 6,
                         color: "var(--text)", cursor: "pointer",
                         fontFamily: "inherit", textAlign: "left",
                       }}>
                <Icon name="file-json-2" size={14} style={{ color: "var(--text-muted)" }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="mono" style={{ fontSize: 12, fontWeight: 600,
                                                    overflow: "hidden", textOverflow: "ellipsis",
                                                    whiteSpace: "nowrap" }}>{r.name}.forgeproject.json</div>
                  <div className="mono" style={{ fontSize: 10.5, color: "var(--text-dim)",
                                                   overflow: "hidden", textOverflow: "ellipsis",
                                                   whiteSpace: "nowrap" }}>{r.path}</div>
                </div>
                <span style={{ fontSize: 11, color: "var(--text-dim)" }}>{r.when}</span>
                <span className="mono" style={{ fontSize: 11, color: "var(--text-muted)", width: 50, textAlign: "right" }}>
                  {r.segs} clips
                </span>
                <span className="mono" style={{ fontSize: 11, color: "var(--text-muted)", width: 50, textAlign: "right" }}>
                  {r.dur}
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>

      <ModalFooter>
        <Button kind="ghost" size="sm" onClick={onCancel}>Cancel</Button>
      </ModalFooter>
    </Modal>
  );
}

// ── Unsaved-changes confirmation ─────────────────────────────────
function UnsavedChangesDialog({ project, savedPath, onDiscard, onSave, onCancel }) {
  const name = savedPath
    ? savedPath.split("/").pop()
    : `${slug(project.name)}.forgeproject.json (unsaved)`;
  return (
    <Modal onClose={onCancel} width={460}
            title="Save changes?"
            icon="alert-triangle"
            iconTone="warn"
            subtitle={
              <>
                <span className="mono" style={{ color: "var(--text)" }}>{name}</span>{" "}
                has unsaved changes.
              </>
            }>
      <div style={{ fontSize: 12.5, color: "var(--text-muted)", lineHeight: 1.5 }}>
        Discarding will lose edits since your last save. Section order, joiners, trim windows,
        audio beds, and overlays will revert to the last saved state.
      </div>

      <ModalFooter>
        <Button kind="ghost" size="sm" onClick={onCancel}>Cancel</Button>
        <Button kind="danger" size="sm" icon="trash-2" onClick={onDiscard}>Don't save</Button>
        <Button kind="primary" size="sm" icon="save" onClick={onSave}>Save and continue</Button>
      </ModalFooter>
    </Modal>
  );
}

// ── Generic modal shell ──────────────────────────────────────────
function Modal({ title, icon, iconTone = "accent", subtitle, width = 480, onClose, children }) {
  ioUseEffect(() => {
    function k(e) { if (e.key === "Escape") onClose(); }
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  const iconColor = {
    accent: "var(--accent-warm)",
    warn:   "var(--warn)",
    danger: "var(--danger)",
  }[iconTone] || "var(--text)";
  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 50,
      background: "rgba(0,0,0,0.65)", display: "grid", placeItems: "center",
    }} onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} style={{
        width, maxHeight: "88vh", display: "flex", flexDirection: "column",
        background: "var(--surface)", border: "1px solid var(--border)",
        borderRadius: 12, boxShadow: "var(--elev-3)", overflow: "hidden",
      }}>
        <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--border)",
                       display: "flex", alignItems: "flex-start", gap: 12 }}>
          {icon && <Icon name={icon} size={16}
                          style={{ color: iconColor, marginTop: 2, flexShrink: 0 }} />}
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 14, fontWeight: 600 }}>{title}</div>
            {subtitle && <div style={{ fontSize: 11.5, color: "var(--text-dim)", marginTop: 3, lineHeight: 1.5 }}>
              {subtitle}
            </div>}
          </div>
          <Button kind="ghost" size="icon" onClick={onClose}><Icon name="x" size={14} /></Button>
        </div>
        <div style={{ padding: 18, flex: 1, minHeight: 0, overflow: "auto" }}>
          {children}
        </div>
      </div>
    </div>
  );
}
function ModalFooter({ children }) {
  return (
    <div style={{ display: "flex", justifyContent: "flex-end", gap: 8,
                   marginTop: 16, paddingTop: 14,
                   borderTop: "1px solid var(--border)" }}>
      {children}
    </div>
  );
}

function slug(s) { return (s || "untitled").toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9_-]/g, ""); }

Object.assign(window, { SaveAsDialog, OpenProjectDialog, UnsavedChangesDialog });


export { Modal, ModalFooter, OpenProjectDialog, PIO_RECENTS, SaveAsDialog, UnsavedChangesDialog, slug };
