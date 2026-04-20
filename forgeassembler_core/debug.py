# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Debug-mode instrumentation for ForgeAssembler.

Off by default. Toggled on from the sidebar (or via `?debug=1` URL
param). When on, `log_event` appends to an in-session event log that
the user can ⚑ Mark and Export as a JSONL click trail — used to file
precise bug reports ("the section-3 content went missing at click 42;
here's the log").

Stays completely inert when debug is off: `log_event` is cheap no-op
guarded by `is_debug_enabled()`. Instrumentation callers swallow all
exceptions so telemetry never breaks the app.

Ports the same shape as FunscriptForge's `ui/streamlit/debug/events.py`
so we accumulate one consistent bug-reporting pattern across the
three liquid-releasing products.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import streamlit as st

_EVENTS_KEY = "_debug_events"
_ENABLED_KEY = "_debug_enabled"
_SESSION_STARTED_KEY = "_debug_session_started"


# ── Core toggle ───────────────────────────────────────────────────────
def is_debug_enabled() -> bool:
    """True when debug mode is on (sidebar toggle or ?debug=1 URL param)."""
    if st.session_state.get(_ENABLED_KEY):
        return True
    try:
        qp = st.query_params
        if qp.get("debug") in ("1", "true", "on"):
            st.session_state[_ENABLED_KEY] = True
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


# ── Event log ─────────────────────────────────────────────────────────
def _events() -> list[dict]:
    if _EVENTS_KEY not in st.session_state:
        st.session_state[_EVENTS_KEY] = []
    return st.session_state[_EVENTS_KEY]


def log_event(kind: str, summary: str, **extra: Any) -> None:
    """Append an event to the session log. No-op when debug is off."""
    if not is_debug_enabled():
        return
    try:
        events = _events()
        events.append({
            "n": len(events) + 1,
            "ts": time.time(),
            "kind": kind,
            "summary": summary,
            "extra": extra,
        })
    except Exception:  # noqa: BLE001
        pass


def hash_project(project: Any) -> str:
    """Short content hash of a Project (via its to_dict). Stable across
    semantically-equivalent projects. Used to stamp "which project
    shape was this?" on an event.
    """
    try:
        blob = json.dumps(project.to_dict(), sort_keys=True, separators=(",", ":"))
    except Exception:  # noqa: BLE001
        return ""
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:10]


def snapshot_session() -> dict[str, Any]:
    """Small, pickle-safe snapshot of key ForgeAssembler session_state
    values. Attached to ⚑ Mark events."""
    ss = st.session_state
    project = ss.get("project")
    snap: dict[str, Any] = {
        "add_target_mode": ss.get("add_target_mode"),
        "add_path_input": ss.get("add_path_input"),
        "editing_section_id": ss.get("editing_section_id"),  # reserved for edit mode
    }
    if project is not None and hasattr(project, "to_dict"):
        try:
            snap["project_hash"] = hash_project(project)
            snap["section_count"] = len(project.sections)
            snap["segment_count"] = sum(
                len(sec.segments) for sec in project.sections
            )
            snap["overlay_count"] = sum(
                len(sec.overlays) for sec in project.sections
            )
            snap["output_folder"] = project.output.folder
            snap["output_basename"] = project.output.basename
            snap["closing_joiner"] = project.output.closing_joiner.joiner_type
        except Exception:  # noqa: BLE001
            pass
    return snap


def mark_issue(note: str) -> dict:
    snap = snapshot_session()
    evt = {
        "n": len(_events()) + 1,
        "ts": time.time(),
        "kind": "marker",
        "summary": f"⚑ {note}" if note else "⚑ Issue noticed here",
        "extra": {"snapshot": snap},
    }
    _events().append(evt)
    return evt


# ── Export ────────────────────────────────────────────────────────────
def _debug_log_dir() -> Path:
    """Where exported debug logs go. Under the app's writable dir when
    the launcher sets FORGEASSEMBLER_DATA_DIR; otherwise `~/.forgeassembler`.
    """
    env = os.environ.get("FORGEASSEMBLER_DATA_DIR")
    if env:
        base = Path(env)
    else:
        base = Path.home() / ".forgeassembler"
    d = base / "debug_logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _session_stem() -> str:
    stem = st.session_state.get(_SESSION_STARTED_KEY)
    if not stem:
        stem = time.strftime("%Y%m%d-%H%M%S")
        st.session_state[_SESSION_STARTED_KEY] = stem
    return stem


def export_log() -> Path:
    path = _debug_log_dir() / f"debug_{_session_stem()}.jsonl"
    with open(path, "w", encoding="utf-8") as fh:
        for evt in _events():
            fh.write(json.dumps(evt, default=str) + "\n")
    return path


def clear_log() -> None:
    st.session_state[_EVENTS_KEY] = []


# ── Sidebar panel ─────────────────────────────────────────────────────
def render_debug_sidebar() -> None:
    """Render the debug-mode toggle + panel in the sidebar. Always
    renders the toggle (users can turn it ON); only renders the event
    panel when debug is enabled — keeps the sidebar quiet for casual
    users."""
    st.sidebar.markdown("---")
    st.sidebar.checkbox(
        "🔧 Debug mode",
        key=_ENABLED_KEY,
        help=(
            "Record a click trail of significant actions so issues "
            "can be reported with precise repro steps. OFF by default."
        ),
    )
    if not is_debug_enabled():
        return

    events = _events()
    st.sidebar.caption(f"**Click {len(events)}** · session `{_session_stem()}`")

    cols = st.sidebar.columns([3, 2])
    with cols[0]:
        if st.button(
            "⚑ Mark this", key="_debug_mark",
            help="Stamp the current moment as an issue. Adds a marker "
                 "event with a full session snapshot.",
            use_container_width=True,
        ):
            mark_issue("Issue noticed here")
            st.toast("Marked. Export the log to share.")
            st.rerun()
    with cols[1]:
        if st.button(
            "Export", key="_debug_export",
            use_container_width=True,
        ):
            try:
                path = export_log()
                st.toast(f"Saved: {path.name}")
                st.sidebar.caption(f"📄 `{path}`")
            except Exception as exc:  # noqa: BLE001
                st.sidebar.error(f"Export failed: {exc}")

    if st.sidebar.button(
        "Clear log", key="_debug_clear",
        help="Drop all recorded events (start the trail fresh).",
    ):
        clear_log()
        st.rerun()

    with st.sidebar.expander(
        f"Recent events ({min(len(events), 20)} of {len(events)})",
        expanded=False,
    ):
        if not events:
            st.caption("No events yet.")
        else:
            for evt in reversed(events[-20:]):
                kind_badge = "⚑" if evt["kind"] == "marker" else "·"
                st.markdown(
                    f"`#{evt['n']:03d}` {kind_badge} **{evt['kind']}** "
                    f"— {evt['summary']}",
                )
