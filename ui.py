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
    instantiate_joiner,
    joiner_specs,
    new_id,
    validate,
)

# Resolve bundled media paths absolutely. Works in dev and PyInstaller bundle.
_APP_DIR = Path(__file__).parent.resolve()
_MEDIA = _APP_DIR / "media"


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

    # Summary stats (live, without ffprobe — will be real in later phase)
    st.subheader("Summary")
    st.write(f"Segments: **{len(segs)}**  ·  Joiners: **{len(joins)}**")
    st.caption("Duration stats populate once ffprobe integration lands.")

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

    st.button(
        "🔨 Forge",
        type="primary",
        use_container_width=True,
        disabled=bool(errors) or not project.items,
        help="Video forging is not implemented yet in this alpha.",
    )


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
