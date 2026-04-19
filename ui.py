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
    BugOverlay,
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
            try:
                import json as _json
                data = _json.loads(uploaded.read().decode("utf-8"))
                st.session_state["project"] = Project.from_dict(data)
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
            st.session_state["project"] = _initial_project()
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
        )
        bug_on = st.checkbox(
            "Corner bug overlay", value=out.bug is not None,
            disabled=not out.produce_video,
        )
        if bug_on and out.bug is None:
            out.bug = BugOverlay(file="")
        elif not bug_on:
            out.bug = None
        if out.bug is not None:
            out.bug.file = st.text_input(
                "Bug PNG path", value=out.bug.file,
                placeholder=r"C:\brand\logo_bug.png",
            )
            out.bug.corner = st.selectbox(
                "Corner", options=["tl", "tr", "bl", "br"],
                index=["tl", "tr", "bl", "br"].index(out.bug.corner),
                format_func=lambda k: {
                    "tl": "Top-left", "tr": "Top-right",
                    "bl": "Bottom-left", "br": "Bottom-right",
                }[k],
            )
            out.bug.opacity = st.slider(
                "Opacity", 0.0, 1.0, float(out.bug.opacity), 0.05,
            )
            out.bug.margin_px = int(st.number_input(
                "Margin (px)", min_value=0, max_value=500,
                value=int(out.bug.margin_px),
            ))

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
                    elif "duration_s" not in sec.leading_joiner.params:
                        sec.leading_joiner.params["duration_s"] = 1.0

            with hcols[1]:
                if sec.leading_joiner.joiner_type == "fade_to_black":
                    sec.leading_joiner.params["duration_s"] = float(st.number_input(
                        "Duration (s)", min_value=0.1, max_value=30.0,
                        value=float(sec.leading_joiner.params.get("duration_s", 1.0)),
                        step=0.5, key=f"jdur_{sec.id}",
                        help="Total transition time. Fades take up to 0.5s on "
                             "each side; longer durations extend the middle hold.",
                    ))
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
                for ov in sec.overlays:
                    ocols = st.columns([1, 5, 3, 2, 1])
                    with ocols[0]:
                        st.caption(
                            "🖼" if ov.kind == "image" else "🎵",
                        )
                    with ocols[1]:
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
                            st.caption(f"pos: {ov.position}")
                        else:
                            st.caption(f"mix: {ov.mix_pct}%")
                    with ocols[4]:
                        if st.button(
                            "✕", key=f"rmov_{ov.id}",
                            help="Remove this overlay",
                        ):
                            sec.overlays = [
                                x for x in sec.overlays if x.id != ov.id
                            ]
                            st.rerun()

            # Trailing-joiner readout: show what happens AFTER this
            # section — i.e. the next section's leading joiner. For the
            # final section we show "→ end of output" so the transition
            # story is complete at a glance.
            if sec_idx + 1 < len(project.sections):
                nxt = project.sections[sec_idx + 1].leading_joiner
                if nxt.joiner_type == "fade_to_black":
                    d = float(nxt.params.get("duration_s", 1.0))
                    st.caption(
                        f"⤴ Transitions OUT with **Fade to black** "
                        f"({d:g}s) into Section {sec_idx + 2}.",
                    )
                else:
                    st.caption(
                        f"⤴ Cuts straight into Section {sec_idx + 2}.",
                    )
            else:
                st.caption("⤴ End of output.")

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

    current_path = st.session_state.get("add_path_input", "").strip()

    target_cols = st.columns([3, 2])
    with target_cols[0]:
        mode_options = ["new_section", "current_section", "overlay"]
        mode_labels = {
            "new_section": "As a NEW section (new chapter)",
            "current_section": "Into the LAST section (cut-join)",
            "overlay": "As an OVERLAY on the LAST section",
        }
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
        if st.session_state["add_target_mode"] == "overlay":
            add_click = False  # overlay uses its own dedicated form below
        else:
            add_click = st.button(
                "Add clips to project",
                type="primary",
                use_container_width=True,
                disabled=not current_path,
            )

    # ── Overlay-mode form ──────────────────────────────────────────
    if st.session_state["add_target_mode"] == "overlay":
        st.caption(
            "Image overlays composite onto the assembled video during "
            "the last section's time window. Audio overlays are in the "
            "schema but not yet rendered — coming in a follow-up.",
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

        pos_cols = st.columns([3, 2, 2])
        with pos_cols[0]:
            ov_position = st.selectbox(
                "Position (image only)",
                options=list(OVERLAY_POSITIONS),
                index=0,
                format_func=lambda k: {
                    "center": "Center",
                    "tl": "Upper-left",
                    "tr": "Upper-right",
                    "bl": "Lower-left",
                    "br": "Lower-right",
                }[k],
                key="ov_position",
            )
        with pos_cols[1]:
            ov_opacity = st.slider(
                "Opacity (image only)",
                min_value=0.0, max_value=1.0, value=1.0, step=0.05,
                key="ov_opacity",
            )
        with pos_cols[2]:
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
                    ))
                    label = (
                        "Image overlay"
                        if kind == "image" else
                        "Audio overlay (not yet rendered)"
                    )
                    st.success(f"{label} added to last section.")
                    st.session_state["pending_add_path"] = ""
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
                    else:
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
