# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""ForgeAssembler Streamlit UI — three tabs over the project model."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st

from forgeassembler_core import (
    ABOUT_MARKDOWN,
    APP_NAME,
    BugOverlay,
    FRAME_RATE_KEYS,
    Joiner as CoreJoiner,
    Output,
    OutputChannels,
    Project,
    ProjectJoiner,
    RESOLUTION_KEYS,
    RESOLUTION_PIXELS,
    Segment,
    TAGLINE,
    VERSION,
    categorize_channels,
    detect_file,
    detect_folder,
    forge_video,
    instantiate_joiner,
    joiner_specs,
    new_id,
    validate,
)

# Resolve bundled media paths absolutely. Works in dev and PyInstaller bundle.
_APP_DIR = Path(__file__).parent.resolve()
_MEDIA = _APP_DIR / "media"


# ── Cached duration probing for sidebar estimate ──────────────────────
@st.cache_data(show_spinner=False)
def _probe_video_ms(path: str, mtime: float, _ffmpeg_exe: str) -> int:
    """Cached wrapper around probe_duration_ms. `mtime` participates in
    the cache key so the entry invalidates when the file is rewritten."""
    from forgeassembler_core.probe import probe_duration_ms
    return probe_duration_ms(path, _ffmpeg_exe)


def _estimate_total_duration_ms(proj: Project) -> int | None:
    """Sum the durations of every item in the project. Returns None if
    ffmpeg isn't available; individual unreadable videos are skipped
    with a zero contribution."""
    from forgeassembler_core.concat_video import _resolve_ffmpeg_exe
    from forgeassembler_core.joiners import instantiate as _instantiate_joiner

    try:
        ffmpeg_exe = _resolve_ffmpeg_exe()
    except RuntimeError:
        return None

    total = 0
    for item in proj.items:
        if isinstance(item, Segment):
            if item.is_still():
                total += int((item.still_duration_s or 0) * 1000)
                continue
            p = Path(item.video)
            if not p.exists():
                continue
            try:
                total += _probe_video_ms(str(p), p.stat().st_mtime, ffmpeg_exe)
            except Exception:  # noqa: BLE001
                continue
        elif isinstance(item, ProjectJoiner):
            try:
                total += _instantiate_joiner(
                    item.joiner_type, item.params,
                ).duration_ms()
            except Exception:  # noqa: BLE001
                continue
    return total


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
if "pending_joiner_type" not in st.session_state:
    st.session_state["pending_joiner_type"] = "none"
if "pending_joiner_params" not in st.session_state:
    st.session_state["pending_joiner_params"] = {"duration_s": 1.0}


project: Project = st.session_state["project"]


# ── Sidebar ───────────────────────────────────────────────────────────
with st.sidebar:
    _l, _c, _r = st.columns([1, 3, 1])
    with _c:
        st.image(str(_MEDIA / "forgeassembler_wordmark.png"), width="stretch")
    st.caption(TAGLINE)
    st.caption(f"Version {VERSION}")

    # Project JSON controls
    with st.expander("Project file", expanded=False):
        uploaded = st.file_uploader(
            "Load a project JSON", type=["json"], key="project_upload"
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

        if project.items and project.output.folder:
            save_path = Path(project.output.folder) / f"{project.output.basename}.forgeproject.json"
            if st.button("Save project JSON", use_container_width=True):
                try:
                    project.save(save_path)
                    st.success(f"Saved to {save_path}")
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Save failed: {exc}")

        if st.button("New project", use_container_width=True):
            st.session_state["project"] = _initial_project()
            st.rerun()

    # Produce what?
    with st.expander("Produce", expanded=True):
        out = project.output
        out.produce_video = st.checkbox("Video (MP4)", value=out.produce_video)
        out.produce_funscripts = st.checkbox("Funscripts", value=out.produce_funscripts)
        if not out.produce_video and not out.produce_funscripts:
            st.error("At least one of Video or Funscripts must be on.")
        st.caption("Chapter markers are always written when video is on.")

    # Output resolution + audio normalize + bug
    with st.expander("Output settings", expanded=False):
        out = project.output
        res_index = (
            list(RESOLUTION_KEYS).index(out.resolution)
            if out.resolution in RESOLUTION_KEYS else 0
        )
        def _res_label(key: str) -> str:
            px = RESOLUTION_PIXELS.get(key)
            return f"{key} ({px[0]}×{px[1]})" if px else f"{key} (first segment)"
        out.resolution = st.selectbox(
            "Resolution",
            options=list(RESOLUTION_KEYS),
            index=res_index,
            format_func=_res_label,
            disabled=not out.produce_video,
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
            "Quality",
            options=q_options,
            index=q_index,
            format_func=lambda k: quality_labels[k],
            disabled=not out.produce_video,
            help="Higher quality = larger file. Most distribution "
                 "sites prefer Medium or Low to keep uploads small.",
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
            "Frame rate",
            options=list(FRAME_RATE_KEYS),
            index=fr_index,
            format_func=lambda k: frame_rate_labels[k],
            disabled=not out.produce_video,
            help="'Match first video' avoids frame drops when sources are "
                 "60 fps. Pick a fixed value to force every clip to it.",
        )
        out.normalize_audio = st.checkbox(
            "Normalize audio loudness (−16 LUFS)",
            value=out.normalize_audio,
            disabled=not out.produce_video,
        )
        # Bug overlay (project-level)
        bug_on = st.checkbox(
            "Corner bug overlay",
            value=out.bug is not None,
            disabled=not out.produce_video,
        )
        if bug_on and out.bug is None:
            out.bug = BugOverlay(file="")
        elif not bug_on:
            out.bug = None
        if out.bug is not None:
            out.bug.file = st.text_input(
                "Bug PNG path",
                value=out.bug.file,
                placeholder=r"C:\brand\logo_bug.png",
            )
            out.bug.corner = st.selectbox(
                "Corner",
                options=["tl", "tr", "bl", "br"],
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
                "Margin (px)", min_value=0, max_value=500, value=int(out.bug.margin_px),
            ))

    # MP4 container metadata (title, artist, date, …).
    with st.expander("Metadata", expanded=False):
        md = project.output.metadata
        st.caption(
            "Embedded in the MP4 container. VLC briefly overlays `title` "
            "on playback; File Explorer / Plex / YouTube read these too."
        )
        md.title = st.text_input("Title", value=md.title or "") or None
        md.artist = st.text_input(
            "Artist / Author", value=md.artist or "",
        ) or None
        md.date = st.text_input(
            "Date",
            value=md.date or "",
            help="e.g. '2026-04-19' or '2026'",
        ) or None
        md.genre = st.text_input("Genre", value=md.genre or "") or None
        md.comment = st.text_area(
            "Comment / description",
            value=md.comment or "",
            height=68,
            help="Free-form. A good home for version notes like 'v1.2 final cut'.",
        ) or None
        md.copyright = st.text_input(
            "Copyright",
            value=md.copyright or "",
            placeholder="© 2026 Liquid Releasing",
        ) or None

    # Output channels (funscripts)
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

    # Project list
    st.subheader("Project list")
    segs = project.segments()
    joins = project.joiners()
    if not project.items:
        st.caption("Empty. Add a segment on the Build tab.")
    else:
        for i, item in enumerate(project.items):
            if isinstance(item, Segment):
                st.markdown(f"**{i + 1}. Segment** · `{Path(item.video).name}`")
            else:
                st.markdown(f"&nbsp;&nbsp;↓ *Joiner: {item.joiner_type}*", unsafe_allow_html=True)
            cols = st.columns([5, 1])
            with cols[1]:
                if st.button("✕", key=f"rm_{item.id}"):
                    project.remove(item.id)
                    st.rerun()

    # Summary stats (live, with cached ffmpeg-duration probe).
    st.subheader("Summary")
    st.write(f"Segments: **{len(segs)}**  ·  Joiners: **{len(joins)}**")

    total_ms = _estimate_total_duration_ms(project)
    if total_ms is not None and total_ms > 0:
        total_s = total_ms / 1000
        mins, secs = divmod(int(total_s), 60)
        st.write(f"Total output: **{mins}m {secs}s**")
        st.caption("Encoding typically 1–2× realtime on modern hardware.")
    elif segs:
        st.caption("Add videos and title cards to estimate duration.")

    # Footer
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


# ── Tab 1: Build ──────────────────────────────────────────────────────
with tab_build:
    st.subheader("Add a segment")
    with st.form("add_segment", clear_on_submit=False):
        path_str = st.text_input(
            "Video file or folder",
            placeholder=r"C:\path\to\clip.mp4  or  C:\path\to\folder",
        )
        add_submit = st.form_submit_button("Add to project")

    if add_submit and path_str:
        p = Path(path_str)
        try:
            if p.is_dir():
                clips = detect_folder(p)
                if not clips:
                    st.warning("No videos detected in that folder.")
                for clip in clips:
                    project.add_segment(Segment(id=new_id("seg"), video=str(clip.video)))
                st.toast(f"Added {len(clips)} segment(s).")
            elif p.is_file():
                clip = detect_file(p)
                project.add_segment(Segment(id=new_id("seg"), video=str(clip.video)))
                st.toast("Segment added.")
            else:
                st.error(f"Path not found: {p}")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Could not add: {exc}")
        st.rerun()

    st.markdown("**Add a title card (PNG still)**")
    with st.form("add_title_card", clear_on_submit=True):
        title_path = st.text_input(
            "PNG file",
            placeholder=r"C:\path\to\title_card.png",
            key="title_card_path",
        )
        col_a, col_b = st.columns(2)
        with col_a:
            title_duration = st.number_input(
                "Hold seconds", min_value=0.1, max_value=60.0,
                value=3.0, step=0.1,
            )
        with col_b:
            title_background = st.selectbox(
                "Background",
                options=["black", "previous_last_frame"],
                format_func=lambda k: {
                    "black": "Black",
                    "previous_last_frame": "Previous segment's last frame",
                }[k],
                index=0,
                help=(
                    "'Previous segment's last frame' freezes the frame "
                    "your previous clip ended on and composites this PNG "
                    "over it. Design the PNG with transparency."
                ),
            )
        add_title = st.form_submit_button("Add title card")

    if add_title and title_path:
        tp = Path(title_path)
        if not tp.is_file():
            st.error(f"PNG not found: {tp}")
        elif tp.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
            st.error(f"Not a supported still-image extension: {tp.suffix}")
        else:
            project.add_segment(Segment(
                id=new_id("seg"),
                video=str(tp),
                still_duration_s=float(title_duration),
                background=title_background,
            ))
            st.toast("Title card added.")
            st.rerun()

    st.divider()
    st.subheader("Joiner for the next slot")
    # Picks the joiner inserted between the LAST segment and the next one added.
    joiner_types = [spec.joiner_type for spec in joiner_specs()]
    selected_type = st.selectbox(
        "Type",
        joiner_types,
        index=joiner_types.index(st.session_state["pending_joiner_type"]),
    )
    st.session_state["pending_joiner_type"] = selected_type
    spec = next(s for s in joiner_specs() if s.joiner_type == selected_type)
    pending_params: dict = {}
    for name, info in spec.params_schema.items():
        if info["type"] == "float":
            val = st.number_input(
                info.get("label", name),
                value=float(st.session_state["pending_joiner_params"].get(name, info.get("default", 0.0))),
                min_value=float(info.get("min", 0.0)),
                max_value=float(info.get("max", 99.0)),
                step=0.1,
                help=info.get("help"),
            )
            pending_params[name] = val
    st.session_state["pending_joiner_params"] = pending_params

    if st.button("Insert joiner after last segment", disabled=not project.segments()):
        project.add_joiner(ProjectJoiner(
            id=new_id("join"),
            joiner_type=selected_type,
            params=pending_params,
        ))
        st.rerun()

    st.divider()
    st.subheader("Output")
    project.output.folder = st.text_input(
        "Output folder", value=project.output.folder or "", placeholder=r"C:\out"
    )
    project.output.basename = st.text_input(
        "Output basename", value=project.output.basename or "combined"
    )

    st.divider()
    st.subheader("Preview")
    st.caption("Heatmap and beatmap preview will land alongside the ffmpeg integration.")

    issues = validate(project)
    errors = [i for i in issues if i.level == "error"]
    warnings = [i for i in issues if i.level == "warning"]
    for w in warnings:
        st.warning(w.message)
    for e in errors:
        st.error(e.message)

    can_forge = (not errors) and bool(project.items) and (
        project.output.produce_video or project.output.produce_funscripts
    )
    if st.button(
        "Forge",
        type="primary",
        use_container_width=True,
        disabled=not can_forge,
    ):
        import re as _re

        from forgeassembler_core.concat_video import _resolve_ffmpeg_exe
        from forgeassembler_core.layout import lay_out
        from forgeassembler_core.probe import probe_duration_ms

        # Live progress strip under the Forge button. Populated from
        # ffmpeg's stderr as the forge runs.
        progress_bar = st.progress(0.0, text="Preparing…")

        _TIME_RE = _re.compile(r"time=(\d+):(\d+):([\d.]+)")
        _SPEED_RE = _re.compile(r"speed=\s*([\d.]+)x")

        with st.status("Forging…", expanded=False) as status:
            try:
                ffmpeg_exe = _resolve_ffmpeg_exe()
                status.write(f"ffmpeg: {ffmpeg_exe}")

                progress_bar.progress(0.0, text="Probing segments…")
                layout = lay_out(
                    project,
                    probe=lambda p: probe_duration_ms(p, ffmpeg_exe),
                )
                total_ms = max(1, layout.total_duration_ms)
                status.write(
                    f"Layout: {len(layout.segments())} segments, "
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

                # Resolve 'source' frame rate up front so we can show
                # the user which fps got chosen.
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
                    # Update the progress bar when ffmpeg prints a
                    # `time=HH:MM:SS.ss` marker.
                    m = _TIME_RE.search(line)
                    if m:
                        h, mm, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
                        current_ms = int((h * 3600 + mm * 60 + s) * 1000)
                        frac = min(1.0, current_ms / total_ms)
                        label = f"Encoding… {frac:.0%}  ({current_ms / 1000:.1f}s / {total_ms / 1000:.1f}s)"
                        sm = _SPEED_RE.search(line)
                        if sm:
                            label += f"   {sm.group(1)}× realtime"
                        progress_bar.progress(frac, text=label)
                    # Also stash every ~20th line into the status detail
                    # so the expander has a tail for debugging.
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
                    status.update(label=f"Forged {out_path.name}",
                                  state="complete")
                    st.success(f"Wrote {out_path}")
                else:
                    progress_bar.empty()
                    status.update(label="Nothing to forge (video off, "
                                  "funscripts not yet wired).",
                                  state="complete")

                if project.output.produce_funscripts:
                    st.info(
                        "Funscript production is not yet wired into the "
                        "UI; expected in the next commit.",
                    )
            except Exception as exc:  # noqa: BLE001
                progress_bar.empty()
                status.update(label="Forge failed", state="error")
                st.error(str(exc))


# ── Tab 2: Joiners ────────────────────────────────────────────────────
with tab_joiners:
    st.subheader("Joiner library")
    st.caption("Available joiner types and their parameters. Select a type on the Build tab before inserting.")
    for spec in joiner_specs():
        with st.container(border=True):
            st.markdown(f"**{spec.display_name}**  ·  `{spec.joiner_type}`")
            st.caption(spec.description)
            if spec.params_schema:
                rows = []
                for name, info in spec.params_schema.items():
                    rows.append([name, info.get("type"), info.get("default"), info.get("label", "")])
                st.dataframe(
                    {"param": [r[0] for r in rows],
                     "type": [r[1] for r in rows],
                     "default": [r[2] for r in rows],
                     "label": [r[3] for r in rows]},
                    hide_index=True,
                    use_container_width=True,
                )


# ── Tab 3: Templates (Phase 2) ────────────────────────────────────────
with tab_templates:
    st.subheader("Joiner templates (Phase 2)")
    st.info(
        "This tab will host the YAML template editor for custom joiners. "
        "You'll compose backgrounds, text layers, image overlays, and audio into "
        "reusable joiner types without writing code.",
        icon="🚧",
    )
    st.code(
        """# Example template (not yet rendered)
type: title_card
duration: 3s
background:
  source: next_video
  frame: first
  darken: 0.7
text:
  content: "Victoria Oats Wild Ride"
  typeface: Bebas Neue
  size: 120pt
  position: center
  style: transparent_letters_outlined
audio: silence
""",
        language="yaml",
    )
