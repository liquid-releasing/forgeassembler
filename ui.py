# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""ForgeAssembler Streamlit UI (v2.0 model).

Build tab shows the project as Sections containing clip rows with
thumbnails, a split-section icon, and inline controls. Sidebar keeps
only output settings + channels. File / folder pickers call the
PyWebView HTTP bridge when available (FORGEASSEMBLER_BRIDGE_PORT) for
native OS dialogs; text-input paste is always a fallback.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

import streamlit as st

from forgeassembler_core import (
    ABOUT_MARKDOWN,
    APP_NAME,
    FRAME_RATE_KEYS,
    Joiner as CoreJoiner,
    OVERLAY_POSITIONS,
    Output,
    OutputChannels,
    Project,
    ProjectJoiner,
    RESOLUTION_KEYS,
    RESOLUTION_PIXELS,
    Section,
    SectionOverlay,
    Segment,
    TAGLINE,
    VERSION,
    categorize_channels,
    detect_file,
    detect_folder,
    detect_folder_tree,
    forge_funscripts,
    forge_video,
    joiner_specs,
    new_id,
    validate,
)

# Resolve bundled media paths absolutely. Works in dev and PyInstaller bundle.
_APP_DIR = Path(__file__).parent.resolve()
_MEDIA = _APP_DIR / "media"


# ── Cached probes + thumbnail extraction ──────────────────────────────
@st.cache_data(show_spinner=False)
def _probe_video_ms(path: str, mtime: float, _ffmpeg_exe: str) -> int:
    from forgeassembler_core.probe import probe_duration_ms
    return probe_duration_ms(path, _ffmpeg_exe)


@st.cache_data(show_spinner=False)
def _thumbnail_bytes(
    path: str, mtime: float, offset_s: float = 1.0,
) -> bytes | None:
    """Return a small preview image for a clip.

    For PNG / still-image clips, returns the file bytes as-is (they're
    already the visual). For videos, extracts a single frame `offset_s`
    seconds into the source file via ffmpeg, scaled to a 160px-wide
    JPG. Returns None if ffmpeg isn't available or the file can't be
    decoded.

    `offset_s` is part of the cache key (via st.cache_data on args),
    so trimmed segments that share a source file but start at
    different points each get their own thumbnail.
    """
    from forgeassembler_core.project import is_still_image
    if is_still_image(path):
        try:
            return Path(path).read_bytes()
        except OSError:
            return None

    try:
        from forgeassembler_core.concat_video import _resolve_ffmpeg_exe
        ffmpeg = _resolve_ffmpeg_exe()
    except (ImportError, RuntimeError):
        return None

    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp.close()
    try:
        result = subprocess.run(
            [
                ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                "-ss", f"{offset_s:g}", "-i", path, "-vframes", "1",
                "-vf", "scale=160:-2", "-q:v", "4", tmp.name,
            ],
            capture_output=True, timeout=15,
        )
        if result.returncode != 0:
            return None
        return Path(tmp.name).read_bytes()
    except (subprocess.TimeoutExpired, OSError):
        return None
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


@st.cache_data(show_spinner=False)
def _detect_channels_cached(folder: str, stem: str, mtime_hint: float) -> list[str]:
    """Return channel names found next to a clip; mtime_hint keys on
    the folder listing so new files invalidate the cache."""
    from forgeassembler_core.detect import funscripts_for_stem
    return sorted(funscripts_for_stem(Path(folder), stem).keys())


@st.cache_data(show_spinner=False)
def _detect_audio_estim_cached(
    folder: str, stem: str, mtime_hint: float,
) -> list[str]:
    """Return haptic-estim audio channel names found next to a clip
    (`stereostim.wav`, `legacy.wav`, `prostate.stereostim.wav`).
    Same caching pattern as `_detect_channels_cached`."""
    from forgeassembler_core.detect import audio_estim_for_stem
    return sorted(audio_estim_for_stem(Path(folder), stem).keys())


def _segment_source_duration_ms(
    seg: Segment, ffmpeg_exe: str | None,
) -> int | None:
    """Source video's full duration (ignoring any trim window).

    Used by the split-at-time UI which needs to show the user the
    full source bounds. Returns None if ffmpeg isn't available or the
    file can't be probed.
    """
    if seg.is_still():
        return int((seg.still_duration_s or 0) * 1000)
    if ffmpeg_exe is None:
        return None
    p = Path(seg.video)
    if not p.exists():
        return None
    try:
        return _probe_video_ms(str(p), p.stat().st_mtime, ffmpeg_exe)
    except Exception:  # noqa: BLE001
        return None


def _segment_duration_ms(seg: Segment, ffmpeg_exe: str | None) -> int | None:
    """Best-effort *effective* duration for a single segment — what it
    contributes to the final timeline after any trim window is applied.

    Stills use their declared still_duration; videos are ffmpeg-probed
    (cached) and then narrowed by `Segment.effective_duration_ms` when
    `trim_start` / `trim_end` are set. Returns None if ffmpeg isn't
    available or the file can't be probed.
    """
    source_ms = _segment_source_duration_ms(seg, ffmpeg_exe)
    if source_ms is None:
        return None
    if seg.is_still():
        return source_ms
    return seg.effective_duration_ms(source_ms)


def _section_duration_ms(sec: Section, ffmpeg_exe: str | None) -> int:
    """Sum of clip durations within a section (ignores the leading
    joiner; section duration is only the clips inside it)."""
    total = 0
    for seg in sec.segments:
        d = _segment_duration_ms(seg, ffmpeg_exe)
        if d is not None:
            total += d
    return total


def _fmt_duration(ms: int) -> str:
    """Return a compact mm:ss label (or h:mm:ss for long durations)."""
    if ms <= 0:
        return "0:00"
    total_s = int(round(ms / 1000))
    h, rem = divmod(total_s, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _estimate_total_duration_ms(proj: Project) -> int | None:
    from forgeassembler_core.concat_video import _resolve_ffmpeg_exe
    from forgeassembler_core.joiners import instantiate as _instantiate_joiner

    try:
        ffmpeg_exe = _resolve_ffmpeg_exe()
    except RuntimeError:
        return None

    total = 0
    for item in proj.items:
        if isinstance(item, Segment):
            d = _segment_duration_ms(item, ffmpeg_exe)
            if d is not None:
                total += d
        elif isinstance(item, ProjectJoiner):
            try:
                total += _instantiate_joiner(
                    item.joiner_type, item.params,
                ).duration_ms()
            except Exception:  # noqa: BLE001
                continue
    return total


# ── PyWebView native-dialog bridge ────────────────────────────────────
def _bridge_url(kind: str, initial: str = "") -> str | None:
    """Call the native-picker HTTP bridge if one is running.

    Returns the picked path, or None if no bridge or the user cancelled.
    `kind` is 'folder' or 'file'. When running as a plain Streamlit dev
    server (no PyWebView parent), returns None so the caller can fall
    back to a text-input flow.
    """
    port = os.environ.get("FORGEASSEMBLER_BRIDGE_PORT")
    if not port:
        return None
    params: dict[str, str] = {}
    if initial:
        params["initial"] = initial
    qs = urllib.parse.urlencode(params) if params else ""
    url = f"http://127.0.0.1:{port}/pick-{kind}"
    if qs:
        url = f"{url}?{qs}"
    try:
        with urllib.request.urlopen(url, timeout=120) as resp:
            if resp.status == 200:
                return resp.read().decode("utf-8")
    except Exception:  # noqa: BLE001
        return None
    return None


# ── Page setup ────────────────────────────────────────────────────────
st.set_page_config(
    page_title=f"{APP_NAME} {VERSION}",
    page_icon="🔨",
    layout="wide",
)


# ── Session state ─────────────────────────────────────────────────────
def _initial_project() -> Project:
    home = Path.home()
    default_out = home / "Videos" / "forgeassembler"
    return Project(output=Output(folder=str(default_out)))


if "project" not in st.session_state:
    st.session_state["project"] = _initial_project()
if "add_target_mode" not in st.session_state:
    st.session_state["add_target_mode"] = "new_section"
if "editing_section_id" not in st.session_state:
    st.session_state["editing_section_id"] = None

# Transfer slot: Browse buttons write a picked path here before
# calling st.rerun(). On the next run — BEFORE the text_input widget
# is instantiated — we move it into the widget's own session-state
# key so the input shows the value. Writing directly to a widget's
# key AFTER the widget has been instantiated in the same run is
# forbidden by Streamlit, so we can't skip this dance.
if "pending_add_path" in st.session_state:
    st.session_state["add_path_input"] = st.session_state.pop(
        "pending_add_path",
    )

project: Project = st.session_state["project"]


# ── Sidebar ───────────────────────────────────────────────────────────
with st.sidebar:
    _l, _c, _r = st.columns([1, 3, 1])
    with _c:
        st.image(str(_MEDIA / "forgeassembler_wordmark.png"), width="stretch")
    st.caption(TAGLINE)
    st.caption(f"Version {VERSION}")

    with st.expander("Project file", expanded=False):
        uploaded = st.file_uploader(
            "Load a project JSON", type=["json"], key="project_upload",
        )
        if uploaded is not None:
            last_id = st.session_state.get("_last_loaded_file_id")
            if uploaded.file_id != last_id:
                try:
                    import json as _json
                    data = _json.loads(uploaded.read().decode("utf-8"))
                    st.session_state["project"] = Project.from_dict(data)
                    st.session_state["_last_loaded_file_id"] = uploaded.file_id
                    # Auto-exit edit mode on load — the focused section ID
                    # from the previous project won't exist in the new one.
                    st.session_state["editing_section_id"] = None
                    try:
                        from forgeassembler_core.debug import log_event, hash_project
                        log_event(
                            "project_load_json",
                            f"Loaded {uploaded.name}",
                            filename=uploaded.name,
                            file_id=uploaded.file_id,
                            size_bytes=uploaded.size,
                            section_count=len(st.session_state["project"].sections),
                            project_hash=hash_project(st.session_state["project"]),
                        )
                    except Exception:  # noqa: BLE001
                        pass
                    st.toast("Project loaded.")
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Could not load project: {exc}")

        if project.sections and project.output.folder:
            save_path = Path(project.output.folder) / (
                f"{project.output.basename}.forgeproject.json"
            )
            if st.button("Save project JSON", use_container_width=True):
                try:
                    project.save(save_path)
                    st.success(f"Saved to {save_path}")
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Save failed: {exc}")

        if st.button("New project", use_container_width=True):
            try:
                from forgeassembler_core.debug import log_event
                old_sections = len(st.session_state["project"].sections)
                log_event(
                    "new_project_clicked",
                    "User clicked New project",
                    sections_dropped=old_sections,
                )
            except Exception:  # noqa: BLE001
                pass
            st.session_state["project"] = _initial_project()
            # Clear the uploader widget + load-tracker so a previously
            # dropped file doesn't re-apply itself on the next rerun.
            st.session_state.pop("project_upload", None)
            st.session_state.pop("_last_loaded_file_id", None)
            st.session_state["editing_section_id"] = None
            st.rerun()

    with st.expander("Produce", expanded=True):
        out = project.output
        out.produce_video = st.checkbox("Video (MP4)", value=out.produce_video)
        out.produce_funscripts = st.checkbox(
            "Funscripts", value=out.produce_funscripts,
        )
        out.produce_audio_estim = st.checkbox(
            "Audio (haptic estim)",
            value=out.produce_audio_estim,
            help=(
                "Concat per-channel haptic-estim audio "
                "(.stereostim.wav / .legacy.wav / .prostate.stereostim.wav) "
                "found alongside source clips. One output WAV per channel "
                "in the project. Off-segments are silence-filled at "
                "48 kHz stereo to keep lockstep with video."
            ),
        )
        if (
            not out.produce_video
            and not out.produce_funscripts
            and not out.produce_audio_estim
        ):
            st.error(
                "At least one of Video / Funscripts / Audio must be on.",
            )
        st.caption("Chapter markers are always written when video is on.")

    with st.expander("Output settings", expanded=False):
        out = project.output
        res_index = (
            list(RESOLUTION_KEYS).index(out.resolution)
            if out.resolution in RESOLUTION_KEYS else 0
        )

        def _res_label(key: str) -> str:
            px = RESOLUTION_PIXELS.get(key)
            return f"{key} ({px[0]}×{px[1]})" if px else f"{key} (first clip)"

        out.resolution = st.selectbox(
            "Resolution", options=list(RESOLUTION_KEYS), index=res_index,
            format_func=_res_label, disabled=not out.produce_video,
        )
        quality_labels = {
            "high": "High — CRF 18 (~10 Mbps 1080p, archive quality)",
            "medium": "Medium — CRF 23 (~4 Mbps 1080p, YouTube default)",
            "low": "Low — CRF 28 (~2 Mbps 1080p, Discord / draft)",
        }
        q_options = list(quality_labels.keys())
        try:
            q_index = q_options.index(out.quality)
        except ValueError:
            q_index = q_options.index("medium")
        out.quality = st.selectbox(
            "Quality", options=q_options, index=q_index,
            format_func=lambda k: quality_labels[k],
            disabled=not out.produce_video,
            help="Higher quality = larger file.",
        )
        frame_rate_labels = {
            "source": "Match first video (auto-detect)",
            "24": "24 fps (cinematic)",
            "30": "30 fps",
            "60": "60 fps (smooth)",
        }
        try:
            fr_index = list(FRAME_RATE_KEYS).index(out.frame_rate)
        except ValueError:
            fr_index = 0
        out.frame_rate = st.selectbox(
            "Frame rate", options=list(FRAME_RATE_KEYS), index=fr_index,
            format_func=lambda k: frame_rate_labels[k],
            disabled=not out.produce_video,
            help="'Match first video' avoids frame drops when sources are 60 fps.",
        )
        out.normalize_audio = st.checkbox(
            "Normalize audio loudness (−16 LUFS)",
            value=out.normalize_audio, disabled=not out.produce_video,
            help=(
                "Recommended ON when sections use audio overlays — balances "
                "levels across sections. Does not rebalance within a section's "
                "mix (use each overlay's Mix % for that)."
            ),
        )
    with st.expander("Metadata", expanded=False):
        md = project.output.metadata
        st.caption(
            "Embedded in the MP4 container. VLC briefly overlays `title` "
            "on playback; File Explorer / Plex / YouTube read these too.",
        )
        md.title = st.text_input("Title", value=md.title or "") or None
        md.artist = st.text_input(
            "Artist / Author", value=md.artist or "",
        ) or None
        md.date = st.text_input(
            "Date", value=md.date or "",
            help="e.g. '2026-04-19' or '2026'",
        ) or None
        md.genre = st.text_input("Genre", value=md.genre or "") or None
        md.comment = st.text_area(
            "Comment / description", value=md.comment or "", height=68,
            help="Free-form. Good home for version notes.",
        ) or None
        md.copyright = st.text_input(
            "Copyright", value=md.copyright or "",
            placeholder="© 2026 Liquid Releasing",
        ) or None

    with st.expander("Output channels", expanded=True):
        oc = project.output_channels
        fs_on = project.output.produce_funscripts
        if not fs_on:
            st.caption("Funscripts production is off; channels are disabled.")
        oc.main = st.checkbox("Main (2D)", value=oc.main, disabled=not fs_on)
        oc.multi_axis = st.checkbox(
            "Multi-axis (pitch/roll/surge/sway/twist)",
            value=oc.multi_axis, disabled=not fs_on,
        )
        oc.three_phase_estim = st.checkbox(
            "3-phase estim (alpha + beta)",
            value=oc.three_phase_estim, disabled=not fs_on,
        )
        oc.prostate = st.checkbox(
            "Prostate channels", value=oc.prostate, disabled=not fs_on,
        )
        st.caption("Phase 2: audio estim, pulse frequency, 4-phase.")

    st.subheader("Summary")
    all_segs = project.segments()
    st.write(
        f"Sections: **{len(project.sections)}**  ·  Clips: **{len(all_segs)}**",
    )
    total_ms = _estimate_total_duration_ms(project)
    if total_ms is not None and total_ms > 0:
        total_s = total_ms / 1000
        mins, secs = divmod(int(total_s), 60)
        st.write(f"Total output: **{mins}m {secs}s**")
        st.caption("Encoding typically 1–2× realtime on modern hardware.")
    elif all_segs:
        st.caption("Add clips to estimate duration.")

    # Debug-mode toggle + optional event panel. Lives above the
    # Liquid Releasing footer so the panel (when expanded) doesn't
    # push the branding off-screen.
    from forgeassembler_core.debug import render_debug_sidebar
    render_debug_sidebar()

    st.divider()
    _fl, _fc, _fr = st.columns([1, 3, 1])
    with _fc:
        st.image(str(_MEDIA / "liquid-releasing-logo.svg"), width="stretch")
    st.markdown(
        """
        <center style="font-size:0.85em; line-height:1.6;">
        © 2026 <a href="https://github.com/liquid-releasing" target="_blank">Liquid Releasing</a><br>
        <a href="https://github.com/liquid-releasing/forgeassembler" target="_blank">ForgeAssembler</a>
        &nbsp;·&nbsp;
        <a href="https://github.com/liquid-releasing/forgeassembler/blob/main/LICENSE" target="_blank">MIT License</a>
        &nbsp;·&nbsp;
        <a href="https://discord.gg/UHdJFhEZF" target="_blank">Discord</a>
        </center>
        """,
        unsafe_allow_html=True,
    )


# ── Tabs ──────────────────────────────────────────────────────────────
tab_build, tab_joiners, tab_templates = st.tabs(["Build", "Joiners", "Templates"])


# ── Helpers used by the Build tab ─────────────────────────────────────
# Single source of truth for overlay-position display labels. Every
# selectbox that offers OVERLAY_POSITIONS should call _POSITION_LABEL
# via format_func — keeping the labels here means adding a new
# position (e.g. ml/mr in 2026-04-20) only needs one touch point.
_POSITION_LABELS: dict[str, str] = {
    "center": "Center",
    "tc": "Top-center",
    "bc": "Bottom-center",
    "tl": "Top-left",
    "tr": "Top-right",
    "ml": "Middle-left",
    "mr": "Middle-right",
    "bl": "Bottom-left",
    "br": "Bottom-right",
}


def _POSITION_LABEL(key: str) -> str:
    """Fallback to the raw key when an unknown position slips through,
    rather than raising KeyError from inside a Streamlit render."""
    return _POSITION_LABELS.get(key, key)


_JOINER_TYPES: tuple[str, ...] = ("none", "fade_to_black")
_JOINER_LABELS = {
    "none": "Cut (no transition)",
    "fade_to_black": "Fade from black",
}


def _add_from_path(
    path_str: str, mode: str, target_section_idx: int = -1,
) -> tuple[int, str]:
    """Resolve a path into clips and add them to the project.

    `target_section_idx` is where `current_section` mode appends. The
    default `-1` (last section) preserves the page-bottom Add Clips
    panel's historical behavior. Edit mode passes the focused section's
    index so adds land in THIS section instead of LAST.

    Returns (added_count, kind) where `kind` is "video", "still", or
    "folder". Raises FileNotFoundError / ValueError on bad input.
    """
    p = Path(path_str).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"Path not found: {p}")

    from forgeassembler_core.project import is_still_image
    new_segments: list[Segment] = []

    if p.is_dir():
        # `detect_folder_tree` falls back to scanning numbered / named
        # subfolders when the picked folder has no videos directly
        # (matches `new-project` CLI semantics: .forge/0/0.mp4 etc).
        clips = detect_folder_tree(p)
        if not clips:
            raise ValueError(
                "No videos detected in that folder or its subfolders.",
            )
        for clip in clips:
            new_segments.append(Segment(
                id=new_id("seg"), video=str(clip.video),
            ))
        kind = "folder"
    elif is_still_image(p):
        new_segments.append(Segment(
            id=new_id("seg"), video=str(p), still_duration_s=3.0,
        ))
        kind = "still"
    else:
        clip = detect_file(p)
        new_segments.append(Segment(id=new_id("seg"), video=str(clip.video)))
        kind = "video"

    if mode == "new_section":
        # ONE new section containing all the clips together.
        project.add_section(Section(
            id=new_id("sec"), segments=new_segments,
        ))
    elif mode == "new_section_per_file":
        # One NEW section per segment. A folder with N clips yields N
        # sections; a single file collapses to one new section. Works
        # the same on an empty project — the previous fallback that
        # lumped everything into one section was a bug.
        for seg in new_segments:
            project.add_section(Section(
                id=new_id("sec"), segments=[seg],
            ))
    else:
        # current_section / overlay / text targets need an existing
        # section. Fall back to creating one if the project is empty
        # so the user's first add still does something useful.
        if not project.sections:
            project.add_section(Section(
                id=new_id("sec"), segments=new_segments,
            ))
        else:
            project.sections[target_section_idx].segments.extend(new_segments)

    return len(new_segments), kind


def _render_add_clips_panel(
    target_section_idx: int,
    allowed_modes: list[str],
    in_edit_mode: bool,
) -> None:
    """Render the Add Clips form. Used in two contexts:

    - **Overview** (no section focused): rendered at page bottom, all
      five mode options available, target = LAST section.
    - **Edit mode**: rendered inside the focused card just above the
      Done editing button. Only the THIS-section / overlay / text
      modes are shown; targets land on the focused section.

    Widget keys are deliberately shared between both contexts so the
    user's typed path / form values persist when entering or leaving
    edit mode.
    """
    if not in_edit_mode:
        st.divider()
    st.subheader(
        "Add clips to this section" if in_edit_mode else "Add clips",
    )

    acols = st.columns([5, 1, 1])
    with acols[0]:
        # Widget's own session_state key is `add_path_input`.
        # Browse buttons stage picked values via `pending_add_path`
        # which is consumed into this key at the top of the run.
        st.text_input(
            "Folder or file path",
            key="add_path_input",
            placeholder=r"C:\path\to\folder   or   C:\path\to\clip.mp4",
            label_visibility="collapsed",
        )

    with acols[1]:
        if st.button(
            "📁 Folder", help="Browse for a folder (scans all videos in it)",
            use_container_width=True,
            key="add_folder_browse",
        ):
            picked = _bridge_url("folder")
            if picked:
                st.session_state["pending_add_path"] = picked
                st.rerun()
            elif os.environ.get("FORGEASSEMBLER_BRIDGE_PORT") is None:
                st.info(
                    "Native file picker is only available in the desktop app. "
                    "Paste a path into the text box instead.",
                )

    with acols[2]:
        if st.button(
            "📄 File", help="Browse for a single video or PNG file",
            use_container_width=True,
            key="add_file_browse",
        ):
            picked = _bridge_url("file")
            if picked:
                st.session_state["pending_add_path"] = picked
                st.rerun()
            elif os.environ.get("FORGEASSEMBLER_BRIDGE_PORT") is None:
                st.info(
                    "Native file picker is only available in the desktop app. "
                    "Paste a path into the text box instead.",
                )

    # Strip whitespace AND any surrounding quotes — Windows' "Copy as
    # path" wraps the path in double quotes, so pasting that string
    # would otherwise fail existence checks on the literal quoted path.
    current_path = st.session_state.get("add_path_input", "").strip()
    if len(current_path) >= 2 and current_path[0] == current_path[-1] and current_path[0] in ('"', "'"):
        current_path = current_path[1:-1].strip()

    target_word = "THIS" if in_edit_mode else "the LAST"
    target_cols = st.columns([3, 2])
    with target_cols[0]:
        all_mode_labels = {
            "new_section": "As ONE NEW section (all clips together)",
            "new_section_per_file": "As SEPARATE NEW sections (one per file)",
            "current_section": f"Into {target_word} section (cut-join)",
            "overlay": f"As an OVERLAY on {target_word} section",
            "text": f"As TEXT on {target_word} section",
        }
        # Modes that require an existing section to target. Hide them
        # entirely on an empty project — a fresh project should only
        # offer "ONE NEW" and "SEPARATE NEW" so the radio doesn't
        # advertise options the user can't actually use.
        modes_needing_section = {"current_section", "overlay", "text"}
        mode_options = [
            m for m in allowed_modes
            if m in all_mode_labels
            and (project.sections or m not in modes_needing_section)
        ]
        mode_labels = {m: all_mode_labels[m] for m in mode_options}
        # Snap the persisted choice back to a valid one if the user
        # had previously selected a section-requiring mode and then
        # cleared the project (or vice-versa).
        if st.session_state["add_target_mode"] not in mode_options:
            st.session_state["add_target_mode"] = mode_options[0]
        # If the persisted mode isn't in the allowed list (e.g. user
        # had "new_section" selected then entered edit mode), snap to
        # the first allowed mode so the radio doesn't crash.
        current_mode = st.session_state["add_target_mode"]
        if current_mode not in mode_options:
            st.session_state["add_target_mode"] = mode_options[0]
            current_mode = mode_options[0]
        # On an empty project, only the new-section modes work, so
        # disable the rest in the label rather than locking the whole
        # radio. (Streamlit's st.radio doesn't support per-option
        # disabling — we just gate via the Add button's disabled flag
        # below, which already checks `project.sections`.)
        st.session_state["add_target_mode"] = st.radio(
            "Add target",
            options=mode_options,
            index=mode_options.index(current_mode),
            format_func=lambda k: mode_labels[k],
            label_visibility="collapsed",
        )
    with target_cols[1]:
        _mode = st.session_state["add_target_mode"]
        if _mode in ("overlay", "text"):
            # Overlay and text modes each render a dedicated form
            # below with their own primary button.
            add_click = False
        else:
            add_click = st.button(
                "Add clips to project",
                type="primary",
                use_container_width=True,
                disabled=not current_path,
                key="add_clips_btn",
            )

    target_label = (
        "this section" if in_edit_mode else "the last section"
    )

    # ── Overlay-mode form ──────────────────────────────────────────
    if st.session_state["add_target_mode"] == "overlay":
        # Peek at the path extension so we can swap image-only
        # controls (Position / Opacity / Scale) for the audio-only
        # Mix slider when the user has an audio file loaded.
        _audio_exts = (".mp3", ".wav", ".m4a", ".flac", ".ogg")
        _path_suffix = Path(current_path).suffix.lower() if current_path else ""
        _is_audio_path = _path_suffix in _audio_exts

        if _is_audio_path:
            st.caption(
                f"Audio overlay mixes into the assembled video during "
                f"{target_label}'s time window. Mix % sets this "
                "overlay's share of the audio — 50% splits it evenly "
                "with the section's main audio; 20% leaves the main "
                "audio mostly intact."
            )
        else:
            st.caption(
                f"Image overlays composite onto the assembled video "
                f"during {target_label}'s time window. Pick a PNG / "
                "JPG / WEBP file for image, MP3 / WAV / M4A for audio."
            )
        ov_cols = st.columns(4)
        with ov_cols[0]:
            ov_start = st.number_input(
                "Start (s, from section start)",
                min_value=0.0, max_value=3600.0, value=0.0, step=0.5,
                key="ov_start",
            )
        with ov_cols[1]:
            ov_duration = st.number_input(
                "Duration (s) · 0 = full section",
                min_value=0.0, max_value=3600.0, value=0.0, step=0.5,
                key="ov_duration",
            )
        with ov_cols[2]:
            ov_fade_in = st.number_input(
                "Fade in (s)",
                min_value=0.0, max_value=10.0, value=0.0, step=0.1,
                key="ov_fade_in",
            )
        with ov_cols[3]:
            ov_fade_out = st.number_input(
                "Fade out (s)",
                min_value=0.0, max_value=10.0, value=0.0, step=0.1,
                key="ov_fade_out",
            )

        pos_cols = st.columns([2, 2, 2, 2])
        with pos_cols[0]:
            ov_position = st.selectbox(
                "Position (image only)",
                options=list(OVERLAY_POSITIONS),
                index=0,
                format_func=_POSITION_LABEL,
                key="ov_position",
                disabled=_is_audio_path,
            )
        with pos_cols[1]:
            ov_opacity = st.slider(
                "Opacity (image only)",
                min_value=0.0, max_value=1.0, value=1.0, step=0.05,
                key="ov_opacity",
                disabled=_is_audio_path,
            )
        with pos_cols[2]:
            if _is_audio_path:
                ov_mix_pct = int(st.slider(
                    "Mix % (audio only)",
                    min_value=0, max_value=100, value=50, step=5,
                    key="ov_mix_pct",
                    help=(
                        "This overlay's share of the audio mix. 50 = "
                        "evenly blended with the section's main audio; "
                        "20 = main audio dominates; 100 = main is muted "
                        "during the overlay window."
                    ),
                ))
                ov_scale_pct = 100
            else:
                ov_scale_pct = int(st.slider(
                    "Scale % (image only)",
                    min_value=10, max_value=200, value=100, step=5,
                    key="ov_scale_pct",
                    help="100 = native size. 50 = half. 200 = double.",
                ))
                ov_mix_pct = 50
        with pos_cols[3]:
            add_overlay_click = st.button(
                "Add overlay",
                type="primary",
                use_container_width=True,
                disabled=not (current_path and project.sections),
                key="add_overlay_btn",
            )

        if add_overlay_click and current_path and project.sections:
            ov_path = Path(current_path).expanduser()
            if not ov_path.is_file():
                st.error(f"Overlay file not found: {ov_path}")
            else:
                suffix = ov_path.suffix.lower()
                image_exts = (".png", ".jpg", ".jpeg", ".webp")
                audio_exts = (".mp3", ".wav", ".m4a", ".flac", ".ogg")
                kind: str | None
                if suffix in image_exts:
                    kind = "image"
                elif suffix in audio_exts:
                    kind = "audio"
                else:
                    st.error(
                        f"Unsupported overlay extension: {suffix}. Use "
                        "PNG/JPG/WEBP for image, MP3/WAV/M4A for audio.",
                    )
                    kind = None
                if kind is not None:
                    project.sections[target_section_idx].overlays.append(SectionOverlay(
                        id=new_id("ov"),
                        kind=kind,  # type: ignore[arg-type]
                        file=str(ov_path),
                        start_s=float(ov_start),
                        duration_s=float(ov_duration),
                        fade_in_s=float(ov_fade_in),
                        fade_out_s=float(ov_fade_out),
                        position=ov_position,  # type: ignore[arg-type]
                        opacity=float(ov_opacity),
                        scale_pct=ov_scale_pct,
                        mix_pct=ov_mix_pct,
                    ))
                    label = (
                        "Image overlay" if kind == "image"
                        else f"Audio overlay (mix {ov_mix_pct}%)"
                    )
                    st.success(f"{label} added to {target_label}.")
                    st.session_state["pending_add_path"] = ""
                    st.rerun()

    # ── Text-mode form ─────────────────────────────────────────────
    if st.session_state["add_target_mode"] == "text":
        st.caption(
            f"Text overlays draw a string on top of the assembled video "
            f"during {target_label}'s time window. Use `\\n` in the "
            "text box for manual line breaks.",
        )

        # Enumerate system fonts once per render. Cheap enough — ~a
        # few hundred entries max on a stock Windows install.
        from forgeassembler_core.fonts import list_fonts
        _fonts = list_fonts()
        _font_stems = [stem for stem, _ in _fonts]
        if not _font_stems:
            st.warning(
                "No system fonts were found. Text overlays need a "
                ".ttf / .otf / .ttc font file installed on the machine."
            )

        tx_cols = st.columns(4)
        with tx_cols[0]:
            tx_start = st.number_input(
                "Start (s, from section start)",
                min_value=0.0, max_value=3600.0, value=0.0, step=0.5,
                key="tx_start",
            )
        with tx_cols[1]:
            tx_duration = st.number_input(
                "Duration (s) · 0 = full section",
                min_value=0.0, max_value=3600.0, value=5.0, step=0.5,
                key="tx_duration",
            )
        with tx_cols[2]:
            tx_fade_in = st.number_input(
                "Fade in (s)",
                min_value=0.0, max_value=10.0, value=0.5, step=0.1,
                key="tx_fade_in",
            )
        with tx_cols[3]:
            tx_fade_out = st.number_input(
                "Fade out (s)",
                min_value=0.0, max_value=10.0, value=0.5, step=0.1,
                key="tx_fade_out",
            )

        tx_row2 = st.columns([2, 2, 2, 2])
        with tx_row2[0]:
            tx_position = st.selectbox(
                "Position",
                options=list(OVERLAY_POSITIONS),
                index=list(OVERLAY_POSITIONS).index("center"),
                format_func=_POSITION_LABEL,
                key="tx_position",
            )
        with tx_row2[1]:
            tx_font = st.selectbox(
                "Font",
                options=_font_stems if _font_stems else [""],
                index=0,
                key="tx_font",
                disabled=not _font_stems,
            )
        with tx_row2[2]:
            tx_font_size = int(st.number_input(
                "Font size",
                min_value=8, max_value=512, value=72, step=4,
                key="tx_font_size",
            ))
        with tx_row2[3]:
            tx_color = st.color_picker(
                "Text color", value="#ffffff", key="tx_color",
            )

        tx_row3 = st.columns([5, 2])
        with tx_row3[0]:
            tx_text = st.text_area(
                "Text",
                value="",
                key="tx_text",
                placeholder="Liquid Releasing\npresents",
                height=80,
            )
        with tx_row3[1]:
            tx_opacity = st.slider(
                "Opacity",
                min_value=0.0, max_value=1.0, value=1.0, step=0.05,
                key="tx_opacity",
            )
            add_text_click = st.button(
                "Add text",
                type="primary",
                use_container_width=True,
                disabled=not (tx_text.strip() and project.sections and _font_stems),
                key="add_text_btn",
            )

        if tx_text.strip():
            st.caption("Preview:")
            st.code(tx_text, language=None)

        if add_text_click and tx_text.strip() and project.sections and _font_stems:
            project.sections[target_section_idx].overlays.append(SectionOverlay(
                id=new_id("ov"),
                kind="text",
                file="",
                start_s=float(tx_start),
                duration_s=float(tx_duration),
                fade_in_s=float(tx_fade_in),
                fade_out_s=float(tx_fade_out),
                position=tx_position,  # type: ignore[arg-type]
                opacity=float(tx_opacity),
                text=tx_text,
                text_color=tx_color,
                font_size=tx_font_size,
                font_family=tx_font,
            ))
            st.success(f"Text overlay added to {target_label}.")
            st.rerun()

    if add_click and current_path:
        try:
            count, kind = _add_from_path(
                current_path,
                st.session_state["add_target_mode"],
                target_section_idx=target_section_idx,
            )
            if kind == "folder":
                st.success(
                    f"Added {count} clip(s) from folder "
                    f"`{Path(current_path).name}`.",
                )
            else:
                st.success(f"Added {kind} clip.")
            # Stage a blank path so the input clears on the next run.
            st.session_state["pending_add_path"] = ""
            st.rerun()
        except (FileNotFoundError, ValueError) as exc:
            st.error(str(exc))
        except Exception as exc:  # noqa: BLE001
            st.error(f"Could not add: {exc}")


_OVERVIEW_ADD_MODES: list[str] = [
    "new_section", "new_section_per_file",
    "current_section", "overlay", "text",
]
# In edit mode the spec called for ONLY the THIS-section / overlay /
# text modes, but dogfood found that empty inserted sections want to
# bulk-load too (e.g. drop a folder of 16 victoriaoats files as 16
# new sections starting from this position). Allow all five — the
# THIS-modes target the focused section as designed; the NEW-section
# modes still append at the END of the project (the existing semantics
# from page-bottom Add Clips). Trade-off: slight label inconsistency
# (THIS vs LAST in the same panel) for full bulk-add flexibility from
# inside edit mode.
_EDIT_ADD_MODES: list[str] = [
    "current_section",
    "new_section",
    "new_section_per_file",
    "overlay",
    "text",
]


def _render_collapsed_section_row(
    sec: Section, sec_idx: int, ffmpeg_exe: str | None,
) -> None:
    """One-line summary card rendered for non-focused sections while
    edit mode is active. ✏ switches focus to this section.

    Spec: ✏ ONLY switches — don't make the whole row clickable.
    Streamlit re-renders frequently; click-anywhere in a row could
    catch a mis-click during a repaint.
    """
    sec_dur_ms = _section_duration_ms(sec, ffmpeg_exe)
    dur_label = (
        f" · {_fmt_duration(sec_dur_ms)}" if sec_dur_ms > 0 else ""
    )
    clip_label = (
        f"{len(sec.segments)} clip" if len(sec.segments) == 1
        else f"{len(sec.segments)} clips"
    )
    with st.container(border=True):
        cols = st.columns([8, 1])
        with cols[0]:
            st.markdown(
                f"**Section {sec_idx + 1}** · "
                f"_{sec.chapter_name()}_ · "
                f"{clip_label}{dur_label}",
            )
        with cols[1]:
            if st.button(
                "📝",
                key=f"editbtn_{sec.id}",
                help="Edit this section",
            ):
                st.session_state["editing_section_id"] = sec.id
                st.rerun()


def _render_split_at_time(
    sec: Section,
    sec_idx: int,
    seg: Segment,
    clip_idx: int,
    ffmpeg_exe: str | None,
) -> None:
    """Render the per-clip ✂ Split-at-time form below a segment row.

    Lets the user enter a timestamp **in the source file's timeline**
    and split the clip at that point. The second piece auto-promotes
    to a new section (= new chapter), reusing `_split_section_here`'s
    overlay-redistribution logic so any section overlays straddling
    the cut also redistribute correctly.
    """
    from forgeassembler_core.project import (
        format_hms_ms, parse_hms_ms, split_segment_at,
    )

    src_ms = _segment_source_duration_ms(seg, ffmpeg_exe)
    cur_start = seg.trim_start_ms()
    cur_end = seg.trim_end_ms()
    if cur_end is None and src_ms is not None:
        cur_end = src_ms

    with st.expander("✂ Split clip at time…", expanded=False):
        if src_ms is not None:
            st.caption(
                f"Source file: `{Path(seg.video).name}` "
                f"({format_hms_ms(src_ms)} long)",
            )
            if cur_end is not None:
                st.caption(
                    f"This piece plays "
                    f"**{format_hms_ms(cur_start)} → {format_hms_ms(cur_end)}** "
                    f"of the source file.",
                )
        else:
            st.caption(
                f"Source file: `{Path(seg.video).name}` "
                "(could not probe duration; bounds shown best-effort).",
            )

        split_input = st.text_input(
            "Split at (timestamp in source file)",
            placeholder="HH:MM:SS.mmm — e.g. 00:30:00.000",
            key=f"split_at_{seg.id}",
            help=(
                "Enter the timestamp from the SOURCE video file where "
                "you want to cut. The clip becomes two pieces; the "
                "second piece becomes a new chapter (its own section)."
            ),
        )
        if not st.button(
            "Split here (becomes new section)",
            key=f"split_apply_{seg.id}",
            use_container_width=True,
        ):
            return

        # ── Validate input ──────────────────────────────────────
        try:
            split_at_ms = parse_hms_ms(split_input)
        except ValueError as exc:
            st.error(f"Invalid timestamp: {exc}")
            return
        if split_at_ms <= cur_start:
            st.error(
                f"Split point must be later than this piece's start "
                f"({format_hms_ms(cur_start)}).",
            )
            return
        if cur_end is not None and split_at_ms >= cur_end:
            st.error(
                f"Split point must be earlier than this piece's end "
                f"({format_hms_ms(cur_end)}).",
            )
            return

        # ── Execute split + auto-promote tail to new section ───
        try:
            head, tail = split_segment_at(seg, split_at_ms)
        except ValueError as exc:
            st.error(f"Could not split: {exc}")
            return
        sec.segments[clip_idx] = head
        sec.segments.insert(clip_idx + 1, tail)
        # Reuse the existing inter-clip splitter to do the section
        # promotion + section-overlay redistribution.
        _split_section_here(sec_idx, clip_idx, ffmpeg_exe)
        st.toast(
            "Split — second piece is a new section (chapter).",
            icon="✂️",
        )
        st.rerun()


def _split_section_here(
    section_idx: int, clip_idx: int, ffmpeg_exe: str | None = None,
) -> None:
    """Split a section so everything AFTER `clip_idx` becomes a new
    section (placed immediately after the current one) with a default
    cut leading joiner.

    Overlays redistribute by their time window:
      * Entirely within the top half → stays on the top section.
      * Entirely within the bottom half → moves to the new section
        with start_s shifted left by the split offset.
      * Straddles the boundary → kept on top (clamped to top's new
        duration) AND duplicated onto bottom (start_s = 0, duration =
        whatever spilled over).
      * Full-section (`duration_s == 0`) → kept on both halves as
        full-section, since the user's intent was "covers the whole
        section."

    `ffmpeg_exe` is needed to probe the top half's duration when video
    overlays straddle the boundary. When None (or probes fail), the
    fallback is to keep all overlays on the top section unchanged.
    """
    import dataclasses  # noqa: PLC0415

    sec = project.sections[section_idx]
    if clip_idx + 1 >= len(sec.segments):
        return  # nothing to split off

    # Compute the split offset in seconds — total duration of the
    # clips that stay on the top section (segments[0..clip_idx]).
    top_segments = sec.segments[: clip_idx + 1]
    bottom_segments = sec.segments[clip_idx + 1:]

    split_offset_ms = 0
    probe_failed = False
    for seg in top_segments:
        d = _segment_duration_ms(seg, ffmpeg_exe)
        if d is None:
            probe_failed = True
            break
        split_offset_ms += d
    split_offset_s = split_offset_ms / 1000.0 if not probe_failed else None

    # Classify each overlay.
    top_overlays: list[SectionOverlay] = []
    bottom_overlays: list[SectionOverlay] = []
    for ov in sec.overlays:
        if split_offset_s is None:
            # Can't compute boundary — keep everything on top, safe fallback.
            top_overlays.append(ov)
            continue

        # Full-section overlay → covers both halves.
        if ov.duration_s == 0:
            top_overlays.append(ov)
            bottom_copy = dataclasses.replace(
                ov, id=new_id("ov"), start_s=0.0,
            )
            bottom_overlays.append(bottom_copy)
            continue

        ov_end_s = ov.start_s + ov.duration_s

        if ov_end_s <= split_offset_s:
            # Entirely in top half — unchanged.
            top_overlays.append(ov)
        elif ov.start_s >= split_offset_s:
            # Entirely in bottom half — shift left by split offset.
            bottom_overlays.append(dataclasses.replace(
                ov,
                id=new_id("ov"),
                start_s=ov.start_s - split_offset_s,
            ))
        else:
            # Straddles the boundary — clamp top, shift+trim bottom.
            top_overlays.append(dataclasses.replace(
                ov,
                duration_s=split_offset_s - ov.start_s,
                # The fade_out belongs to the bottom half now; zero it
                # on the top so the visible content doesn't fade out
                # mid-section unexpectedly.
                fade_out_s=0.0,
            ))
            bottom_overlays.append(dataclasses.replace(
                ov,
                id=new_id("ov"),
                start_s=0.0,
                duration_s=ov_end_s - split_offset_s,
                # Symmetrically, the fade_in already happened on top.
                fade_in_s=0.0,
            ))

    sec.segments = top_segments
    sec.overlays = top_overlays
    new_sec = Section(
        id=new_id("sec"),
        segments=bottom_segments,
        overlays=bottom_overlays,
    )
    project.sections.insert(section_idx + 1, new_sec)


# ── Tab 1: Build ──────────────────────────────────────────────────────
with tab_build:
    st.subheader("Project")

    if not project.sections:
        st.caption(
            "Empty project — add a folder or file below to get started.",
        )

    # Resolve ffmpeg once up-front for per-clip / per-section probes.
    # Cached probe helper silently skips when the exe isn't available.
    _ffmpeg_exe_for_ui: str | None
    try:
        from forgeassembler_core.concat_video import _resolve_ffmpeg_exe
        _ffmpeg_exe_for_ui = _resolve_ffmpeg_exe()
    except (ImportError, RuntimeError):
        _ffmpeg_exe_for_ui = None

    # ── Existing sections, each rendered as a bordered card ───────
    editing_section_id = st.session_state.get("editing_section_id")
    for sec_idx, sec in enumerate(project.sections):
        # When edit mode is focused on a different section, render this
        # one as a one-line summary instead of the full card. The
        # focused section AND the no-edit-active default both fall
        # through to the existing full-card rendering below.
        if editing_section_id is not None and editing_section_id != sec.id:
            _render_collapsed_section_row(sec, sec_idx, _ffmpeg_exe_for_ui)
            continue

        is_editing_this = editing_section_id == sec.id
        with st.container(border=True):
            # Section header row: leading joiner / fade params / name /
            # ✏ edit (when not currently focused) / 🗑 remove
            hcols = st.columns([2, 3, 3, 1, 1])
            with hcols[0]:
                cur_jtype = sec.leading_joiner.joiner_type
                if cur_jtype not in _JOINER_TYPES:
                    cur_jtype = "none"
                new_jtype = st.selectbox(
                    "Transition in",
                    options=list(_JOINER_TYPES),
                    index=list(_JOINER_TYPES).index(cur_jtype),
                    format_func=lambda k: _JOINER_LABELS[k],
                    key=f"jtype_{sec.id}",
                    label_visibility="collapsed",
                )
                if new_jtype != sec.leading_joiner.joiner_type:
                    sec.leading_joiner.joiner_type = new_jtype
                    if new_jtype == "none":
                        sec.leading_joiner.params.pop("duration_s", None)
                        sec.leading_joiner.params.pop("fade_s", None)
                    elif new_jtype == "fade_to_black":
                        sec.leading_joiner.params.setdefault("duration_s", 5.0)
                        sec.leading_joiner.params.setdefault("fade_s", 1.0)

            with hcols[1]:
                if sec.leading_joiner.joiner_type == "fade_to_black":
                    _hc, _fc = st.columns([1, 1])
                    with _hc:
                        sec.leading_joiner.params["duration_s"] = float(
                            st.number_input(
                                "Hold (s)",
                                min_value=0.0, max_value=30.0,
                                value=float(sec.leading_joiner.params.get(
                                    "duration_s", 5.0,
                                )),
                                step=0.5, key=f"jhold_{sec.id}",
                                help="Solid-black hold between the fade-out "
                                     "on the previous section and the fade-in "
                                     "on this one. Adds to total duration.",
                            )
                        )
                    with _fc:
                        sec.leading_joiner.params["fade_s"] = float(
                            st.number_input(
                                "Fade (s)",
                                min_value=0.0, max_value=10.0,
                                value=float(sec.leading_joiner.params.get(
                                    "fade_s", 1.0,
                                )),
                                step=0.5, key=f"jfade_{sec.id}",
                                help="Per-side fade duration. Fades happen "
                                     "within the adjacent clips — don't add "
                                     "to total duration.",
                            )
                        )
                else:
                    st.caption(
                        "Hard cut — clips inside this section cut straight together.",
                    )

            with hcols[2]:
                sec.name = st.text_input(
                    "Section name",
                    value=sec.name or "",
                    placeholder=sec.chapter_name(),
                    key=f"name_{sec.id}",
                    label_visibility="collapsed",
                    help="Optional. Becomes the MP4 chapter title. "
                         "Leave blank to use the first clip's filename.",
                ) or None

            with hcols[3]:
                # ✏ enters edit mode by focusing this section. Hidden
                # when this section is already focused (Done editing
                # at the bottom is the exit affordance for that case).
                if not is_editing_this:
                    if st.button(
                        "📝",
                        key=f"editbtn_top_{sec.id}",
                        help="Edit this section (collapses the others)",
                    ):
                        st.session_state["editing_section_id"] = sec.id
                        st.rerun()

            with hcols[4]:
                if st.button(
                    "🗑️", key=f"rmsec_{sec.id}",
                    help="Remove this section (and its clips)",
                ):
                    # Auto-exit edit mode if we just deleted the
                    # focused section.
                    if st.session_state.get("editing_section_id") == sec.id:
                        st.session_state["editing_section_id"] = None
                    project.remove_section(sec.id)
                    st.rerun()

            # ── Insert above / below (focused section only) ──────
            # Inserts an empty Section at the chosen index with default
            # "none" (Cut) leading joiner. Focus auto-jumps to the new
            # section so the next user gesture (drop a title-card path
            # in Add Clips) lands there immediately — matches the spec
            # "add something here" intent.
            if is_editing_this:
                ins_cols = st.columns([2, 2, 6])
                with ins_cols[0]:
                    if st.button(
                        "⬆ Insert above",
                        key=f"insup_{sec.id}",
                        help="Insert a new empty section before this one",
                        use_container_width=True,
                    ):
                        new_sec = Section(id=new_id("sec"))
                        project.sections.insert(sec_idx, new_sec)
                        st.session_state["editing_section_id"] = new_sec.id
                        st.rerun()
                with ins_cols[1]:
                    if st.button(
                        "⬇ Insert below",
                        key=f"insdn_{sec.id}",
                        help="Insert a new empty section after this one",
                        use_container_width=True,
                    ):
                        new_sec = Section(id=new_id("sec"))
                        project.sections.insert(sec_idx + 1, new_sec)
                        st.session_state["editing_section_id"] = new_sec.id
                        st.rerun()

            sec_dur_ms = _section_duration_ms(sec, _ffmpeg_exe_for_ui)
            sec_dur_label = (
                f" · **{_fmt_duration(sec_dur_ms)}**"
                if sec_dur_ms > 0 else ""
            )
            st.markdown(
                f"**Section {sec_idx + 1}** · "
                f"{len(sec.segments)} clip(s){sec_dur_label} · chapter: "
                f"_{sec.chapter_name()}_",
            )

            # ── Clip rows (with split-here gaps between consecutive
            # clips). The split affordance lives BETWEEN clips, not on
            # them — splitting happens at a boundary, and putting the
            # button on the clip row was easy to misread as "delete
            # this clip" (✂ = cut = remove in many users' mental
            # models). 🔪 + "Split here" + tooltip make the action
            # explicit and the boundary visible.
            for clip_idx, seg in enumerate(sec.segments):
                row = st.container(border=False)
                with row:
                    cols = st.columns([1, 6, 1, 1, 1])
                    vpath = Path(seg.video)
                    mtime = vpath.stat().st_mtime if vpath.exists() else 0.0

                    with cols[0]:
                        # Extract the thumbnail 1s INTO this piece's
                        # trim window (not into the source file). Two
                        # halves of a split clip share `seg.video` but
                        # have different `trim_start`s, so this is what
                        # makes them visually distinct in the UI.
                        thumb_offset_s = (seg.trim_start_ms() / 1000.0) + 1.0
                        thumb = _thumbnail_bytes(
                            str(vpath), mtime, thumb_offset_s,
                        )
                        if thumb:
                            st.image(thumb, width=120)
                        else:
                            st.caption("(no preview)")

                    with cols[1]:
                        st.markdown(f"**{vpath.name}**")
                        # Duration line first — lets users size audio
                        # overlays and title cards without leaving the UI.
                        dur_ms = _segment_duration_ms(seg, _ffmpeg_exe_for_ui)
                        if seg.is_still():
                            dur_caption = (
                                f"Still image · {seg.still_duration_s or 0:g}s hold"
                            )
                        elif dur_ms is not None and dur_ms > 0:
                            dur_caption = (
                                f"Duration: {_fmt_duration(dur_ms)} "
                                f"({dur_ms / 1000:.1f}s)"
                            )
                        else:
                            dur_caption = "Duration: (not probed)"
                        st.caption(dur_caption)

                        if seg.is_still():
                            pass  # already covered in duration caption
                        else:
                            # Detected funscript channels next to the clip
                            folder = vpath.parent
                            mtime = (
                                folder.stat().st_mtime
                                if folder.exists() else 0.0
                            )
                            channels: list[str] = []
                            try:
                                channels = _detect_channels_cached(
                                    str(folder), vpath.stem, mtime,
                                )
                            except Exception:  # noqa: BLE001
                                pass
                            if channels:
                                st.caption(
                                    "Funscripts: " + ", ".join(channels),
                                )
                            else:
                                st.caption("No funscripts detected")

                            # Detected haptic-estim audio next to the clip.
                            # Shown only when something exists — silent
                            # for the common "no estim audio" case so the
                            # row doesn't grow a noisy "no audio" line on
                            # every clip in non-haptic projects.
                            audio_channels: list[str] = []
                            try:
                                audio_channels = _detect_audio_estim_cached(
                                    str(folder), vpath.stem, mtime,
                                )
                            except Exception:  # noqa: BLE001
                                pass
                            if audio_channels:
                                # `audio_estim_for_stem` returns keys like
                                # "stereostim.wav" / "legacy.wav" /
                                # "prostate.stereostim.wav" — strip the
                                # ".wav" for compactness.
                                pretty = [
                                    k.replace(".wav", "")
                                    for k in audio_channels
                                ]
                                st.caption(
                                    "Audio (estim): " + ", ".join(pretty),
                                )

                    with cols[2]:
                        # Still-image duration editor in-place
                        if seg.is_still():
                            seg.still_duration_s = float(st.number_input(
                                "s", min_value=0.1, max_value=60.0,
                                value=float(seg.still_duration_s or 3.0),
                                step=0.5,
                                key=f"dur_{seg.id}",
                                label_visibility="collapsed",
                            ))

                    with cols[3]:
                        # 🔄 Replace — file-only swap. Keeps section
                        # overlays, audio settings, joiner, etc. — only
                        # the underlying video changes. Funscripts
                        # auto_detect re-scans next render because the
                        # vpath.stem (cache key) changed; explicit
                        # mode keeps the existing map but warns the
                        # user since channel layout likely won't line
                        # up with the new file.
                        if st.button(
                            "🔄", key=f"replace_{seg.id}",
                            help=(
                                "Replace this clip's video file. "
                                "Section overlays + audio settings stay; "
                                "funscripts re-scan automatically."
                            ),
                        ):
                            picked = _bridge_url("file")
                            if picked:
                                seg.video = picked
                                if (
                                    seg.funscripts_source == "explicit"
                                    and seg.explicit_funscripts
                                ):
                                    st.toast(
                                        "Replaced — explicit funscripts may "
                                        "not line up with new video channels. "
                                        "Review or switch to auto-detect.",
                                        icon="⚠️",
                                    )
                                st.rerun()
                            elif os.environ.get(
                                "FORGEASSEMBLER_BRIDGE_PORT",
                            ) is None:
                                st.info(
                                    "Replace needs the desktop app's native "
                                    "file picker. Edit the project JSON "
                                    "manually if running in the browser."
                                )

                    with cols[4]:
                        if st.button(
                            "✕", key=f"rm_{seg.id}",
                            help="Remove this clip",
                        ):
                            project.remove(seg.id)
                            st.rerun()

                # ✂ Split-at-time form for video clips. Lets the user
                # cut INSIDE a single video at a given source-file
                # timestamp; the second piece auto-promotes to a new
                # section (= new chapter). One feature, four uses:
                # trim-start (split + delete head), trim-end (split +
                # delete tail), multi-chapter (split + keep both),
                # mid-video fade (split + set fade_to_black on the
                # tail's leading joiner).
                if not seg.is_still():
                    _render_split_at_time(
                        sec, sec_idx, seg, clip_idx, _ffmpeg_exe_for_ui,
                    )

                # Inter-clip "Split here" affordance. Renders BETWEEN
                # this clip and the next; never after the last clip
                # (nothing to split off). The new section gets all
                # clips from clip_idx+1 onward; this section keeps
                # 0..clip_idx.
                if clip_idx + 1 < len(sec.segments):
                    split_cols = st.columns([2, 4, 6])
                    with split_cols[1]:
                        if st.button(
                            "🔪 Split here",
                            key=f"split_{seg.id}",
                            help=(
                                f"Split section into two between "
                                f"`{Path(sec.segments[clip_idx].video).name}` "
                                f"and `{Path(sec.segments[clip_idx + 1].video).name}`. "
                                f"Clips below this point move to a new "
                                f"section."
                            ),
                            use_container_width=True,
                        ):
                            _split_section_here(
                                sec_idx, clip_idx, _ffmpeg_exe_for_ui,
                            )
                            st.rerun()

            if not sec.segments:
                # Caption adapts: in edit mode the Add Clips panel is
                # right inside this card with the radio already on the
                # focused-section target, so just say "drop a clip
                # below." In overview mode the panel is at page bottom
                # and the radio needs to be switched.
                if is_editing_this:
                    st.caption(
                        "Empty section — drop a path in the Add Clips "
                        "form below to fill it.",
                    )
                else:
                    st.caption(
                        "Empty section — click 📝 to focus this section, "
                        "then add clips inside it.",
                    )

            # ── Section overlays list ───────────────────────────
            if sec.overlays:
                st.markdown("**Overlays** (section-timed, top-to-bottom):")
                for ov_idx, ov in enumerate(sec.overlays):
                    ocols = st.columns([1, 5, 3, 2, 1])
                    with ocols[0]:
                        _kind_icon = {
                            "image": "🖼", "audio": "🎵", "text": "📝",
                        }.get(ov.kind, "?")
                        st.caption(_kind_icon)
                    with ocols[1]:
                        if ov.kind == "text":
                            # Show a short preview of the text content;
                            # truncate long strings and collapse newlines
                            # so the row stays compact.
                            _preview = ov.text.replace("\n", " · ")
                            if len(_preview) > 40:
                                _preview = _preview[:37] + "…"
                            st.caption(f"`{_preview}`")
                        else:
                            st.caption(f"`{Path(ov.file).name}`")
                    with ocols[2]:
                        dur_label = (
                            f"{ov.duration_s:g}s" if ov.duration_s > 0
                            else "full section"
                        )
                        st.caption(
                            f"@ {ov.start_s:g}s · {dur_label}",
                        )
                    with ocols[3]:
                        if ov.kind == "image":
                            scale_label = (
                                "" if ov.scale_pct == 100
                                else f" · {ov.scale_pct}%"
                            )
                            st.caption(f"pos: {ov.position}{scale_label}")
                        elif ov.kind == "text":
                            st.caption(
                                f"pos: {ov.position} · "
                                f"{ov.font_family or '?'} {ov.font_size}px",
                            )
                        else:
                            st.caption(f"mix: {ov.mix_pct}%")
                    with ocols[4]:
                        if st.button(
                            "✕",
                            # Scope by section index + overlay position so
                            # duplicate ov.id values (e.g. same ID reused
                            # across sections in hand-edited JSON) don't
                            # crash the widget tree.
                            key=f"rmov_s{sec_idx}_i{ov_idx}_{ov.id}",
                            help="Remove this overlay",
                        ):
                            sec.overlays = [
                                x for x in sec.overlays if x.id != ov.id
                            ]
                            st.rerun()

            # Trailing-joiner picker — symmetric with the leading-joiner
            # picker at the top of the section. For non-last sections,
            # this IS the next section's leading_joiner (two views, one
            # source of truth — editing either keeps them in sync). For
            # the last section, it drives `output.closing_joiner` which
            # fades the final video + audio to black/silence.
            is_last = sec_idx + 1 >= len(project.sections)
            if is_last:
                trailing = project.output.closing_joiner
                close_labels = {
                    "none": "Cut (hard end)",
                    "fade_to_black": "Fade to black",
                }
                key_suffix = "close"
                end_caption = "⤴ End of output."
                dur_help = (
                    "Video and audio fade together over this duration "
                    "at the very end of the output."
                )
            else:
                trailing = project.sections[sec_idx + 1].leading_joiner
                close_labels = {
                    "none": f"Cut into Section {sec_idx + 2}",
                    "fade_to_black": "Fade to black",
                }
                key_suffix = f"out_{sec.id}"
                end_caption = f"⤴ Into Section {sec_idx + 2}."
                dur_help = (
                    "Fade-to-black bridge between this section and the "
                    "next. Matches the next section's leading-joiner "
                    "picker (editing either stays in sync)."
                )

            tcols = st.columns([2, 3, 3])
            with tcols[0]:
                cur_ttype = trailing.joiner_type
                if cur_ttype not in _JOINER_TYPES:
                    cur_ttype = "none"
                new_ttype = st.selectbox(
                    "Select joiner",
                    options=list(_JOINER_TYPES),
                    index=list(_JOINER_TYPES).index(cur_ttype),
                    format_func=lambda k: close_labels[k],
                    key=f"jtype_{key_suffix}",
                    label_visibility="collapsed",
                )
                if new_ttype != trailing.joiner_type:
                    trailing.joiner_type = new_ttype
                    if new_ttype == "none":
                        trailing.params.pop("duration_s", None)
                        trailing.params.pop("fade_s", None)
                    elif new_ttype == "fade_to_black":
                        trailing.params.setdefault("duration_s", 5.0)
                        trailing.params.setdefault("fade_s", 1.0)

            with tcols[1]:
                if trailing.joiner_type == "fade_to_black":
                    if is_last:
                        # Closing fade has nothing to fade INTO — just
                        # fade the tail of existing content out. Show
                        # Fade only; ignore Hold here.
                        trailing.params["fade_s"] = float(
                            st.number_input(
                                "Fade (s)",
                                min_value=0.1, max_value=10.0,
                                value=float(trailing.params.get("fade_s", 1.0)),
                                step=0.5,
                                key=f"jfade_{key_suffix}",
                                help=(
                                    "Length of the closing fade-out on "
                                    "the final video + audio."
                                ),
                            )
                        )
                    else:
                        _hc, _fc = st.columns([1, 1])
                        with _hc:
                            trailing.params["duration_s"] = float(
                                st.number_input(
                                    "Hold (s)",
                                    min_value=0.0, max_value=30.0,
                                    value=float(trailing.params.get("duration_s", 5.0)),
                                    step=0.5,
                                    key=f"jhold_{key_suffix}",
                                    help=dur_help,
                                )
                            )
                        with _fc:
                            trailing.params["fade_s"] = float(
                                st.number_input(
                                    "Fade (s)",
                                    min_value=0.0, max_value=10.0,
                                    value=float(trailing.params.get("fade_s", 1.0)),
                                    step=0.5,
                                    key=f"jfade_{key_suffix}",
                                    help="Per-side fade duration.",
                                )
                            )
                else:
                    st.caption(
                        "End hard — no closing fade." if is_last
                        else "Hard cut into the next section.",
                    )
            with tcols[2]:
                st.caption(end_caption)

            # ── Add clips panel (in-card, focused section) ──────
            # When this section is being edited, the Add Clips form
            # lives here instead of at page bottom — keeps the user's
            # eyes on the section they're operating on. Radio modes
            # are filtered to operations that target an existing
            # section (no "create NEW section" options).
            if is_editing_this:
                _render_add_clips_panel(
                    target_section_idx=sec_idx,
                    allowed_modes=_EDIT_ADD_MODES,
                    in_edit_mode=True,
                )

            # ── Done editing button (focused section only) ──────
            # Bottom-of-card placement matches the Liquid Releasing
            # convention of putting primary CTAs at the bottom.
            if is_editing_this:
                if st.button(
                    "Done editing",
                    key=f"done_edit_{sec.id}",
                    type="primary",
                    use_container_width=True,
                ):
                    st.session_state["editing_section_id"] = None
                    st.rerun()

    # ── Add clips panel (overview / page bottom) ─────────────
    # In edit mode the Add Clips form is rendered inside the
    # focused section's card just above 'Done editing'. The
    # page-bottom rendering here is the overview default.
    if st.session_state.get("editing_section_id") is None:
        _render_add_clips_panel(
            target_section_idx=-1,
            allowed_modes=_OVERVIEW_ADD_MODES,
            in_edit_mode=False,
        )


    # ── Output folder + basename (kept on Build tab) ──────────────
    st.divider()
    st.subheader("Output file")
    project.output.folder = st.text_input(
        "Output folder",
        value=project.output.folder or "",
        placeholder=r"C:\out",
    )
    project.output.basename = st.text_input(
        "Output basename",
        value=project.output.basename or "combined",
    )

    # ── Validation + Forge ────────────────────────────────────────
    st.divider()
    issues = validate(project)
    errors = [i for i in issues if i.level == "error"]
    warnings = [i for i in issues if i.level == "warning"]
    for w in warnings:
        st.warning(w.message)
    for e in errors:
        st.error(e.message)

    can_forge = (not errors) and bool(project.segments()) and (
        project.output.produce_video
        or project.output.produce_funscripts
        or project.output.produce_audio_estim
    )
    if st.button(
        "Forge", type="primary", use_container_width=True,
        disabled=not can_forge,
    ):
        import re as _re

        from forgeassembler_core.concat_video import _resolve_ffmpeg_exe
        from forgeassembler_core.layout import lay_out
        from forgeassembler_core.probe import probe_duration_ms

        # Debug instrumentation: stamp the forge click with a project
        # snapshot so post-mortem questions like "was section 3 in the
        # project at forge time?" can be answered from the log.
        try:
            from forgeassembler_core.debug import log_event, hash_project
            _oc = project.output_channels
            log_event(
                "forge_clicked",
                f"Forge clicked — {len(project.sections)} section(s)",
                project_hash=hash_project(project),
                section_count=len(project.sections),
                segment_count=sum(len(s.segments) for s in project.sections),
                overlay_count=sum(len(s.overlays) for s in project.sections),
                produce_video=project.output.produce_video,
                produce_funscripts=project.output.produce_funscripts,
                output_channels={
                    "main": _oc.main, "multi_axis": _oc.multi_axis,
                    "three_phase_estim": _oc.three_phase_estim,
                    "prostate": _oc.prostate,
                },
                output_folder=project.output.folder,
                output_basename=project.output.basename,
                closing_joiner=project.output.closing_joiner.joiner_type,
                resolution=project.output.resolution,
                frame_rate=project.output.frame_rate,
            )
        except Exception:  # noqa: BLE001
            pass

        progress_bar = st.progress(0.0, text="Preparing…")
        _TIME_RE = _re.compile(r"time=(\d+):(\d+):([\d.]+)")
        _SPEED_RE = _re.compile(r"speed=\s*([\d.]+)x")

        with st.status("Forging…", expanded=False) as status:
            try:
                ffmpeg_exe = _resolve_ffmpeg_exe()
                status.write(f"ffmpeg: {ffmpeg_exe}")

                progress_bar.progress(0.0, text="Probing clips…")
                layout = lay_out(
                    project,
                    probe=lambda p: probe_duration_ms(p, ffmpeg_exe),
                )
                total_ms = max(1, layout.total_duration_ms)
                status.write(
                    f"Layout: {len(layout.segments())} clip(s), "
                    f"total {total_ms / 1000:.1f}s",
                )

                resolution_override = None
                if (
                    project.output.produce_video
                    and project.output.resolution == "source"
                ):
                    status.write(
                        "Note: 'source' resolution not yet auto-probed; "
                        "falling back to 1920x1080.",
                    )
                    resolution_override = (1920, 1080)

                frame_rate_override = None
                if project.output.produce_video:
                    from forgeassembler_core.concat_video import (
                        _resolve_source_frame_rate,
                    )
                    frame_rate_override = _resolve_source_frame_rate(
                        project, ffmpeg_exe,
                    )
                    if frame_rate_override is not None:
                        status.write(
                            f"Frame rate: matched source → "
                            f"{frame_rate_override} fps",
                        )

                def _log(line: str) -> None:
                    m = _TIME_RE.search(line)
                    if m:
                        h, mm, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
                        current_ms = int((h * 3600 + mm * 60 + s) * 1000)
                        frac = min(1.0, current_ms / total_ms)
                        label = (
                            f"Encoding… {frac:.0%}  "
                            f"({current_ms / 1000:.1f}s / {total_ms / 1000:.1f}s)"
                        )
                        sm = _SPEED_RE.search(line)
                        if sm:
                            label += f"   {sm.group(1)}× realtime"
                        progress_bar.progress(frac, text=label)
                    _log.count = getattr(_log, "count", 0) + 1  # type: ignore[attr-defined]
                    if _log.count % 20 == 0:  # type: ignore[attr-defined]
                        status.write(line)

                if project.output.produce_video:
                    progress_bar.progress(0.0, text="Encoding… 0%")
                    out_path = forge_video(
                        project, layout,
                        ffmpeg_exe=ffmpeg_exe,
                        resolution_override=resolution_override,
                        frame_rate_override=frame_rate_override,
                        log_callback=_log,
                    )
                    progress_bar.progress(1.0, text=f"Done — {out_path.name}")
                    status.update(
                        label=f"Forged {out_path.name}", state="complete",
                    )
                    st.success(f"Wrote {out_path}")
                else:
                    progress_bar.empty()
                    status.update(
                        label="Video pipeline off", state="complete",
                    )

                if project.output.produce_funscripts:
                    status.write("Assembling funscripts…")
                    try:
                        written = forge_funscripts(project, layout)
                    except Exception as fexc:  # noqa: BLE001
                        st.error(f"Funscript forge failed: {fexc}")
                        try:
                            from forgeassembler_core.debug import log_event
                            log_event(
                                "forge_funscripts_failed",
                                f"Funscript forge raised: {fexc}",
                                error_type=type(fexc).__name__,
                            )
                        except Exception:  # noqa: BLE001
                            pass
                    else:
                        try:
                            from forgeassembler_core.debug import log_event
                            log_event(
                                "forge_funscripts_done",
                                f"Wrote {len(written)} funscript file(s)",
                                files=[p.name for p in written],
                                count=len(written),
                            )
                        except Exception:  # noqa: BLE001
                            pass
                        if written:
                            st.success(
                                f"Wrote {len(written)} funscript file(s): "
                                + ", ".join(p.name for p in written),
                            )
                        else:
                            st.info(
                                "No funscripts written — no selected "
                                "channel had any actions across the project.",
                            )

                if project.output.produce_audio_estim:
                    status.write("Concatenating estim audio channels…")
                    try:
                        from forgeassembler_core.concat_audio_estim import (
                            forge_audio_estim,
                        )
                        written_audio = forge_audio_estim(
                            project, layout, ffmpeg_exe=ffmpeg_exe,
                        )
                    except Exception as aexc:  # noqa: BLE001
                        st.error(f"Audio-estim concat failed: {aexc}")
                        try:
                            from forgeassembler_core.debug import log_event
                            log_event(
                                "forge_audio_estim_failed",
                                f"Audio-estim concat raised: {aexc}",
                                error_type=type(aexc).__name__,
                            )
                        except Exception:  # noqa: BLE001
                            pass
                    else:
                        try:
                            from forgeassembler_core.debug import log_event
                            log_event(
                                "forge_audio_estim_done",
                                f"Wrote {len(written_audio)} audio file(s)",
                                files=[p.name for p in written_audio],
                                count=len(written_audio),
                            )
                        except Exception:  # noqa: BLE001
                            pass
                        if written_audio:
                            st.success(
                                f"Wrote {len(written_audio)} estim audio "
                                "file(s): "
                                + ", ".join(p.name for p in written_audio),
                            )
                        else:
                            st.info(
                                "No estim audio written — no segment had a "
                                ".stereostim.wav / .legacy.wav / "
                                ".prostate.stereostim.wav sibling.",
                            )
            except Exception as exc:  # noqa: BLE001
                import traceback as _tb
                progress_bar.empty()
                status.update(label="Forge failed", state="error")
                # Echo full stack to the launcher's stderr so the
                # captured log tells us the root cause on failures.
                print(
                    "Forge failed with exception:", file=sys.stderr,
                )
                _tb.print_exc(file=sys.stderr)
                st.error(f"{type(exc).__name__}: {exc}")
                with st.expander("Full traceback", expanded=False):
                    st.code(_tb.format_exc())


# ── Tab 2: Joiners (reference) ────────────────────────────────────────
with tab_joiners:
    st.subheader("Joiner library")
    st.caption(
        "Available joiner types and their parameters. Section "
        "transitions (above) pick from these.",
    )
    for spec in joiner_specs():
        with st.container(border=True):
            st.markdown(f"**{spec.display_name}**  ·  `{spec.joiner_type}`")
            st.caption(spec.description)
            if spec.params_schema:
                rows = []
                for name, info in spec.params_schema.items():
                    # Stringify `default` so the column has a uniform
                    # string dtype — pyarrow/pandas refuses to mix e.g.
                    # 0.0 (float) and '#000000' (str) in one column.
                    default_raw = info.get("default")
                    default_str = (
                        "" if default_raw is None else str(default_raw)
                    )
                    rows.append([
                        name,
                        str(info.get("type", "")),
                        default_str,
                        info.get("label", ""),
                    ])
                st.dataframe(
                    {
                        "param": [r[0] for r in rows],
                        "type": [r[1] for r in rows],
                        "default": [r[2] for r in rows],
                        "label": [r[3] for r in rows],
                    },
                    hide_index=True,
                    use_container_width=True,
                )


# ── Tab 3: Templates (Phase 2) ────────────────────────────────────────
with tab_templates:
    st.subheader("Joiner templates (Phase 2)")
    st.info(
        "This tab will host the YAML template editor for custom joiners.",
        icon="🚧",
    )
