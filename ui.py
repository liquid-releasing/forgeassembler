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
def _thumbnail_bytes(path: str, mtime: float) -> bytes | None:
    """Return a small preview image for a clip.

    For PNG / still-image clips, returns the file bytes as-is (they're
    already the visual). For videos, extracts a single frame at ~1s in
    via ffmpeg, scaled to a 160px-wide JPG. Returns None if ffmpeg
    isn't available or the file can't be decoded.
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
                "-ss", "1", "-i", path, "-vframes", "1",
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


def _segment_duration_ms(seg: Segment, ffmpeg_exe: str | None) -> int | None:
    """Best-effort duration for a single segment — ffmpeg probe for
    videos (cached), declared still_duration for PNGs. Returns None if
    ffmpeg isn't available or the file can't be probed."""
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
            st.rerun()

    with st.expander("Produce", expanded=True):
        out = project.output
        out.produce_video = st.checkbox("Video (MP4)", value=out.produce_video)
        out.produce_funscripts = st.checkbox(
            "Funscripts", value=out.produce_funscripts,
        )
        if not out.produce_video and not out.produce_funscripts:
            st.error("At least one of Video or Funscripts must be on.")
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
        <a href="https://discord.gg/sZWCqgxY" target="_blank">Discord</a>
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


def _add_from_path(path_str: str, mode: str) -> tuple[int, str]:
    """Resolve a path into clips and add them to the project.

    Returns (added_count, kind) where `kind` is "video", "still", or
    "folder". Raises FileNotFoundError / ValueError on bad input so
    the caller can surface a clear error.
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

    if mode == "new_section" or not project.sections:
        project.add_section(Section(
            id=new_id("sec"), segments=new_segments,
        ))
    elif mode == "new_section_per_file":
        # One NEW section per segment. A folder with N clips yields N
        # sections; a single file collapses to the same behavior as
        # "new_section".
        for seg in new_segments:
            project.add_section(Section(
                id=new_id("sec"), segments=[seg],
            ))
    else:
        project.sections[-1].segments.extend(new_segments)

    return len(new_segments), kind


def _split_section_here(section_idx: int, clip_idx: int) -> None:
    """Split a section so everything AFTER `clip_idx` becomes a new
    section (placed immediately after the current one in the project)
    with a default cut leading joiner."""
    sec = project.sections[section_idx]
    if clip_idx + 1 >= len(sec.segments):
        return  # nothing to split off
    new_sec = Section(
        id=new_id("sec"),
        segments=sec.segments[clip_idx + 1:],
    )
    sec.segments = sec.segments[: clip_idx + 1]
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
    for sec_idx, sec in enumerate(project.sections):
        with st.container(border=True):
            # Section header row: leading joiner / section name / remove
            hcols = st.columns([2, 3, 3, 1])
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
                if st.button(
                    "🗑", key=f"rmsec_{sec.id}",
                    help="Remove this section (and its clips)",
                ):
                    project.remove_section(sec.id)
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

            # ── Clip rows ────────────────────────────────────────
            for clip_idx, seg in enumerate(sec.segments):
                row = st.container(border=False)
                with row:
                    cols = st.columns([1, 6, 1, 1, 1])
                    vpath = Path(seg.video)
                    mtime = vpath.stat().st_mtime if vpath.exists() else 0.0

                    with cols[0]:
                        thumb = _thumbnail_bytes(str(vpath), mtime)
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
                            channels: list[str] = []
                            try:
                                channels = _detect_channels_cached(
                                    str(folder), vpath.stem,
                                    folder.stat().st_mtime if folder.exists() else 0.0,
                                )
                            except Exception:  # noqa: BLE001
                                pass
                            if channels:
                                st.caption(
                                    "Funscripts: " + ", ".join(channels),
                                )
                            else:
                                st.caption("No funscripts detected")

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
                        # Split-section icon (disabled for the last clip —
                        # nothing after it to split off).
                        can_split = clip_idx + 1 < len(sec.segments)
                        if st.button(
                            "✂", key=f"split_{seg.id}",
                            help=(
                                "Split section here — clips after this one "
                                "move to a new section"
                            ),
                            disabled=not can_split,
                        ):
                            _split_section_here(sec_idx, clip_idx)
                            st.rerun()

                    with cols[4]:
                        if st.button(
                            "✕", key=f"rm_{seg.id}",
                            help="Remove this clip",
                        ):
                            project.remove(seg.id)
                            st.rerun()

            if not sec.segments:
                st.caption(
                    "Empty section — add clips using the 'Add clips' "
                    "panel below and switch target to 'Current section'.",
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

    # ── Add clips panel ───────────────────────────────────────────
    st.divider()
    st.subheader("Add clips")

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

    target_cols = st.columns([3, 2])
    with target_cols[0]:
        mode_options = [
            "new_section", "new_section_per_file",
            "current_section", "overlay", "text",
        ]
        mode_labels = {
            "new_section": "As ONE NEW section (all clips together)",
            "new_section_per_file": "As SEPARATE NEW sections (one per file)",
            "current_section": "Into the LAST section (cut-join)",
            "overlay": "As an OVERLAY on the LAST section",
            "text": "As TEXT on the LAST section",
        }
        # When the project has no sections, only "new_section" is a
        # valid target — snap the mode back so the radio isn't stuck
        # on a disabled option after "New project".
        if not project.sections:
            st.session_state["add_target_mode"] = "new_section"
        current_mode = st.session_state["add_target_mode"]
        try:
            m_idx = mode_options.index(current_mode)
        except ValueError:
            m_idx = 0
        st.session_state["add_target_mode"] = st.radio(
            "Add target",
            options=mode_options,
            index=m_idx,
            format_func=lambda k: mode_labels[k],
            label_visibility="collapsed",
            disabled=not project.sections,
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
            )

    # ── Overlay-mode form ──────────────────────────────────────────
    if st.session_state["add_target_mode"] == "overlay":
        # Peek at the path extension so we can swap image-only
        # controls (Position / Opacity / Scale) for the audio-only
        # Mix slider when the user has an audio file loaded.
        _image_exts = (".png", ".jpg", ".jpeg", ".webp")
        _audio_exts = (".mp3", ".wav", ".m4a", ".flac", ".ogg")
        _path_suffix = Path(current_path).suffix.lower() if current_path else ""
        _is_audio_path = _path_suffix in _audio_exts

        if _is_audio_path:
            st.caption(
                "Audio overlay mixes into the assembled video during "
                "the last section's time window. Mix % sets this "
                "overlay's share of the audio — 50% splits it evenly "
                "with the section's main audio; 20% leaves the main "
                "audio mostly intact."
            )
        else:
            st.caption(
                "Image overlays composite onto the assembled video "
                "during the last section's time window. Pick a PNG / "
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
        # Image inputs get rendered regardless (keeps their keys
        # alive in session_state even when the path is audio), but
        # disabled for audio paths so their values are obviously
        # inert. For audio paths the third slot becomes Mix %.
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
                    project.sections[-1].overlays.append(SectionOverlay(
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
                    st.success(f"{label} added to last section.")
                    st.session_state["pending_add_path"] = ""
                    st.rerun()

    # ── Text-mode form ─────────────────────────────────────────────
    if st.session_state["add_target_mode"] == "text":
        st.caption(
            "Text overlays draw a string on top of the assembled video "
            "during the last section's time window. Use `\\n` in the "
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
            )

        if tx_text.strip():
            st.caption("Preview:")
            st.code(tx_text, language=None)

        if add_text_click and tx_text.strip() and project.sections and _font_stems:
            project.sections[-1].overlays.append(SectionOverlay(
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
            st.success("Text overlay added to last section.")
            st.rerun()

    if add_click and current_path:
        try:
            count, kind = _add_from_path(
                current_path,
                st.session_state["add_target_mode"],
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
        project.output.produce_video or project.output.produce_funscripts
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
