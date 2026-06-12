/* @esm-converted */
import React from 'react';
const { useState, useEffect } = React;
import { App } from './App';
import { BuildTab } from './BuildTab';

// Drag-and-drop infrastructure for Build tab clip/section reordering.
//
// Native HTML5 DnD, kept simple. Three concerns:
//
//   1. A render-time React Context that holds:
//        - `drag`     — what's being dragged ({kind, id, fromSectionId?})
//        - `over`     — where it would land ({kind, id, position})
//        - `setOver(x)`, `setDrag(x)` setters
//      The provider lives in BuildTab; reducer lives in App and is
//      called via `onReorderClip` / `onReorderSection` props.
//
//   2. `useDraggable(opts)` — wires the events on a row/header so it
//      becomes a drag source. Returns props to spread onto the element.
//
//   3. `useDroppable(opts)` — wires onDragOver / onDrop / onDragLeave
//      and computes whether the cursor is in the top or bottom half
//      of the element ("before" vs "after").
//
//   4. `<DropLine />` — a 2px accent stripe rendered above the
//      target when `over` matches.
//
// Drag images are suppressed; the existing row stays in place and a
// faint accent stripe shows the drop slot.

const { createContext: dndContext, useContext: dndUseContext, useRef: dndRef } = React;

const DragDropContext = dndContext({ drag: null, over: null,
  setDrag: () => {}, setOver: () => {},
  onReorderClip: () => {}, onReorderSection: () => {} });

function DragDropProvider({ children, onReorderClip, onReorderSection }) {
  const [drag, setDrag] = React.useState(null);
  const [over, setOver] = React.useState(null);
  // Reset on Escape
  React.useEffect(() => {
    function k(e) { if (e.key === "Escape") { setDrag(null); setOver(null); } }
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, []);
  return (
    <DragDropContext.Provider value={{ drag, over, setDrag, setOver, onReorderClip, onReorderSection }}>
      {children}
    </DragDropContext.Provider>
  );
}

function useDragDrop() { return dndUseContext(DragDropContext); }

// ── useDraggable: clip or section drag source ─────────────────────
function useDraggable({ kind, id, fromSectionId }) {
  const ctx = useDragDrop();
  return {
    draggable: true,
    onDragStart: (e) => {
      // Suppress the default browser drag image — we render our own
      // visual treatment.
      try {
        const ghost = document.createElement("div");
        ghost.style.position = "absolute"; ghost.style.left = "-9999px";
        document.body.appendChild(ghost);
        e.dataTransfer.setDragImage(ghost, 0, 0);
        setTimeout(() => document.body.removeChild(ghost), 0);
      } catch { /* noop */ }
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", `${kind}:${id}`);
      ctx.setDrag({ kind, id, fromSectionId });
    },
    onDragEnd: () => { ctx.setDrag(null); ctx.setOver(null); },
    "data-dragging": ctx.drag?.kind === kind && ctx.drag?.id === id ? "true" : null,
  };
}

// ── useDroppable: row or header drop target ──────────────────────
// `accept`: "clip" | "section"
// `sectionId`: when accepting clip drops, what section this slot is in
function useDroppable({ accept, id, sectionId }) {
  const ctx = useDragDrop();
  const ref = dndRef();
  const handlers = {
    onDragOver: (e) => {
      if (!ctx.drag || ctx.drag.kind !== accept) return;
      // Don't drop on self
      if (ctx.drag.id === id) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      const r = e.currentTarget.getBoundingClientRect();
      const position = (e.clientY - r.top) < r.height / 2 ? "before" : "after";
      const cur = ctx.over;
      if (!cur || cur.id !== id || cur.position !== position || cur.kind !== accept) {
        ctx.setOver({ kind: accept, id, position, sectionId });
      }
    },
    onDragLeave: (e) => {
      // Only clear if we're leaving the entire element
      const r = e.currentTarget.getBoundingClientRect();
      if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) {
        if (ctx.over?.id === id) ctx.setOver(null);
      }
    },
    onDrop: (e) => {
      if (!ctx.drag || ctx.drag.kind !== accept || !ctx.over) return;
      e.preventDefault();
      const { drag, over } = ctx;
      if (accept === "clip") {
        ctx.onReorderClip(drag.id, drag.fromSectionId, over.sectionId, over.id, over.position);
      } else if (accept === "section") {
        ctx.onReorderSection(drag.id, over.id, over.position);
      }
      ctx.setDrag(null);
      ctx.setOver(null);
    },
  };
  const isHoverTarget = ctx.over?.kind === accept && ctx.over?.id === id;
  return { ref, handlers, hoverPosition: isHoverTarget ? ctx.over.position : null };
}

// ── DropLine — visual indicator between rows ─────────────────────
function DropLine({ on }) {
  return (
    <div style={{
      height: on ? 4 : 0,
      margin: on ? "2px 0" : 0,
      background: "var(--accent)",
      borderRadius: 2,
      boxShadow: on ? "0 0 0 1px rgba(255,75,75,0.25), 0 0 8px rgba(255,75,75,0.45)" : "none",
      transition: "height 80ms, margin 80ms",
    }} />
  );
}

// ── reducers exposed to App ──────────────────────────────────────
function reorderClipInProject(project, clipId, fromSectionId, toSectionId, anchorClipId, position) {
  const next = { ...project, sections: project.sections.map(s => ({ ...s, segments: [...s.segments] })) };
  let movingClip = null;
  // Remove from source
  for (const s of next.sections) {
    const i = s.segments.findIndex(c => c.id === clipId);
    if (i !== -1) { movingClip = s.segments.splice(i, 1)[0]; break; }
  }
  if (!movingClip) return project;
  // Insert into destination
  const dest = next.sections.find(s => s.id === toSectionId);
  if (!dest) return project;
  const ai = dest.segments.findIndex(c => c.id === anchorClipId);
  const insertAt = ai === -1
    ? dest.segments.length
    : (position === "before" ? ai : ai + 1);
  dest.segments.splice(insertAt, 0, movingClip);
  return next;
}

function reorderSectionInProject(project, sectionId, anchorSectionId, position) {
  const sections = [...project.sections];
  const fromIdx = sections.findIndex(s => s.id === sectionId);
  if (fromIdx === -1) return project;
  const [moving] = sections.splice(fromIdx, 1);
  const ai = sections.findIndex(s => s.id === anchorSectionId);
  const insertAt = ai === -1
    ? sections.length
    : (position === "before" ? ai : ai + 1);
  sections.splice(insertAt, 0, moving);
  return { ...project, sections };
}

Object.assign(window, {
  DragDropProvider, useDragDrop, useDraggable, useDroppable, DropLine,
  reorderClipInProject, reorderSectionInProject,
});


export { DragDropContext, DragDropProvider, DropLine, reorderClipInProject, reorderSectionInProject, useDragDrop, useDraggable, useDroppable };
