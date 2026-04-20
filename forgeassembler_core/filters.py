# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""ffmpeg filter-chain string builders.

Pure functions that return filter_complex fragments. No ffmpeg is
invoked here; concat_video.py composes these fragments into one graph.

Labels (the `[name]` tokens) are caller-supplied; this module performs
no label validation. Callers should use consistent naming conventions
like `v_seg0`, `a_seg0`, `v_seg0_bug`, `vout`, `afinal`, etc.
"""

from __future__ import annotations

from typing import Iterable

from .project import BugCorner


# ── Segment normalization (scale + pad + optional color temp) ─────────
def normalize_segment_filter(
    in_label: str,
    out_label: str,
    width: int,
    height: int,
    color_temperature_k: int | None = None,
) -> str:
    """Scale the input down to fit WxH keeping aspect, pad to exact WxH,
    reset sample aspect, and optionally apply a color-temperature shift.

    Produces a single comma-separated filter chain, e.g.::

        [v_in]scale=1920:1080:force_original_aspect_ratio=decrease,
        pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1[v_out]
    """
    chain = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        f"setsar=1"
    )
    if color_temperature_k is not None:
        chain += f",colortemperature=temperature={int(color_temperature_k)}"
    return f"[{in_label}]{chain}[{out_label}]"


# ── Bug overlay (project-level corner PNG) ────────────────────────────
def corner_position_expr(corner: BugCorner, margin_px: int) -> tuple[str, str]:
    """Return `(x_expr, y_expr)` strings usable in the overlay filter.

    The expressions use ffmpeg's `W`, `H`, `w`, `h` variables (main
    width/height and overlay width/height).
    """
    m = int(margin_px)
    if corner == "tl":
        return (f"{m}", f"{m}")
    if corner == "tr":
        return (f"W-w-{m}", f"{m}")
    if corner == "bl":
        return (f"{m}", f"H-h-{m}")
    if corner == "br":
        return (f"W-w-{m}", f"H-h-{m}")
    raise ValueError(f"Unknown corner: {corner!r}")


def bug_prepare_filter(
    in_label: str,
    out_label: str,
    opacity: float,
) -> str:
    """Apply an alpha-based opacity to a bug PNG input.

    Uses `format=rgba` to ensure an alpha channel is present, then
    `colorchannelmixer=aa=<opacity>` to multiply the alpha. Required
    before the overlay filter if opacity < 1.0.
    """
    opacity = max(0.0, min(1.0, float(opacity)))
    return (
        f"[{in_label}]format=rgba,"
        f"colorchannelmixer=aa={opacity:g}[{out_label}]"
    )


def bug_overlay_filter(
    in_video_label: str,
    in_bug_label: str,
    out_label: str,
    corner: BugCorner,
    margin_px: int,
) -> str:
    """Composite a prepared bug overlay onto a video stream at a corner."""
    x_expr, y_expr = corner_position_expr(corner, margin_px)
    return (
        f"[{in_video_label}][{in_bug_label}]"
        f"overlay=x={x_expr}:y={y_expr}:format=auto"
        f"[{out_label}]"
    )


# ── Joiner transitions ────────────────────────────────────────────────
def fade_to_black_xfade(
    a_video_label: str,
    b_video_label: str,
    out_label: str,
    duration_s: float,
    offset_s: float,
) -> str:
    """Build an `xfade=transition=fadeblack` filter between two streams.

    `offset_s` is the timestamp (measured on the A stream) where the
    transition begins. `duration_s` is the transition length.
    """
    return (
        f"[{a_video_label}][{b_video_label}]"
        f"xfade=transition=fadeblack:duration={duration_s:g}:offset={offset_s:g}"
        f"[{out_label}]"
    )


def fade_to_black_audio_acrossfade(
    a_audio_label: str,
    b_audio_label: str,
    out_label: str,
    duration_s: float,
) -> str:
    """Cross-fade audio in lockstep with a `fade_to_black` video xfade."""
    return (
        f"[{a_audio_label}][{b_audio_label}]"
        f"acrossfade=d={duration_s:g}:c1=tri:c2=tri"
        f"[{out_label}]"
    )


# ── Concat (video + audio in lockstep) ────────────────────────────────
def concat_filter(
    stream_pairs: Iterable[tuple[str, str]],
    out_video_label: str,
    out_audio_label: str,
) -> str:
    """Concat N (video, audio) stream pairs into a single (v, a) pair.

    stream_pairs is an iterable of `(v_label, a_label)`.
    Emits ffmpeg's `concat=n=N:v=1:a=1` form.
    """
    pairs = list(stream_pairs)
    if not pairs:
        raise ValueError("concat_filter requires at least one stream pair")
    prefix = "".join(f"[{v}][{a}]" for v, a in pairs)
    return (
        f"{prefix}concat=n={len(pairs)}:v=1:a=1"
        f"[{out_video_label}][{out_audio_label}]"
    )


# ── Audio loudness normalization ──────────────────────────────────────
def loudnorm_filter(
    in_label: str,
    out_label: str,
    integrated_lufs: float = -16.0,
    true_peak_dbfs: float = -1.5,
    loudness_range_lu: float = 11.0,
) -> str:
    """Single-pass EBU R128 loudness normalize.

    Defaults to the YouTube reference level (−16 LUFS integrated,
    −1.5 dBFS true peak, 11 LU range).
    """
    return (
        f"[{in_label}]"
        f"loudnorm=I={integrated_lufs:g}:TP={true_peak_dbfs:g}:LRA={loudness_range_lu:g}"
        f"[{out_label}]"
    )


# ── Image overlay (per-segment / per-section) ────────────────────────
# Long names used by the per-clip Overlay dataclass; short aliases
# (tl/tr/bl/br) match the SectionOverlay and BugCorner conventions.
_POSITION_EXPRS: dict[str, tuple[str, str]] = {
    "center": ("(W-w)/2", "(H-h)/2"),
    "top-left": ("0", "0"),
    "top-right": ("W-w", "0"),
    "bottom-left": ("0", "H-h"),
    "bottom-right": ("W-w", "H-h"),
    "top-center": ("(W-w)/2", "0"),
    "bottom-center": ("(W-w)/2", "H-h"),
    "tl": ("0", "0"),
    "tr": ("W-w", "0"),
    "bl": ("0", "H-h"),
    "br": ("W-w", "H-h"),
    "tc": ("(W-w)/2", "0"),
    "bc": ("(W-w)/2", "H-h"),
}


def image_overlay_filter(
    in_video_label: str,
    in_image_label: str,
    out_label: str,
    position: str = "center",
    start_s: float = 0.0,
    end_s: float | None = None,
    opacity: float = 1.0,
    fade_in_s: float = 0.0,
    fade_out_s: float = 0.0,
) -> str:
    """Composite an image onto a video stream at a named position.

    The image is re-formatted with an alpha channel and preprocessed:
    `colorchannelmixer=aa` applies `opacity`; `fade=alpha=1` at the
    start/end of the visible window applies `fade_in_s` / `fade_out_s`
    (both only take effect if > 0 and, for fade_out, if `end_s` is known).
    Visibility outside [start_s, end_s] is enforced via overlay's
    `enable` expression.
    """
    if position not in _POSITION_EXPRS:
        raise ValueError(
            f"Unknown overlay position: {position!r}. "
            f"Known: {', '.join(sorted(_POSITION_EXPRS))}"
        )
    x_expr, y_expr = _POSITION_EXPRS[position]

    # Preprocess the image: alpha channel + optional opacity + fades.
    prep_parts: list[str] = ["format=rgba"]
    if opacity < 1.0:
        prep_parts.append(
            f"colorchannelmixer=aa={max(0.0, min(1.0, opacity)):g}",
        )
    if fade_in_s > 0:
        prep_parts.append(
            f"fade=t=in:st={start_s:g}:d={fade_in_s:g}:alpha=1",
        )
    if fade_out_s > 0 and end_s is not None:
        fade_out_start = max(0.0, end_s - fade_out_s)
        prep_parts.append(
            f"fade=t=out:st={fade_out_start:g}:d={fade_out_s:g}:alpha=1",
        )

    image_label = in_image_label
    prefix = ""
    if len(prep_parts) > 1:  # more than just format=rgba
        prepared = f"{in_image_label}_prep"
        prefix = f"[{in_image_label}]{','.join(prep_parts)}[{prepared}];"
        image_label = prepared

    enable = ""
    if end_s is not None:
        enable = f":enable='between(t,{start_s:g},{end_s:g})'"
    elif start_s > 0:
        enable = f":enable='gte(t,{start_s:g})'"

    return (
        f"{prefix}[{in_video_label}][{image_label}]"
        f"overlay=x={x_expr}:y={y_expr}{enable}:format=auto"
        f"[{out_label}]"
    )


# ── Text overlay (section-scoped) ─────────────────────────────────────
# Positions use drawtext's `tw`/`th` (text width/height) and `W`/`H`
# (main frame size). Corners get a small breathing-room margin so the
# glyphs don't sit flush against the edge.
_TEXT_POSITION_EXPRS: dict[str, tuple[str, str]] = {
    "center": ("(W-tw)/2", "(H-th)/2"),
    "tc": ("(W-tw)/2", "20"),
    "bc": ("(W-tw)/2", "H-th-20"),
    "tl": ("20", "20"),
    "tr": ("W-tw-20", "20"),
    "bl": ("20", "H-th-20"),
    "br": ("W-tw-20", "H-th-20"),
}


def _escape_drawtext(text: str) -> str:
    """Escape a string for inline use in ffmpeg's drawtext `text=...`.

    drawtext treats `\\`, `:`, `'`, and `%` specially inside a
    single-quoted value. Newlines pass through as literal line breaks.
    """
    return (
        text.replace("\\", "\\\\")
            .replace(":", "\\:")
            .replace("'", "\\'")
            .replace("%", "\\%")
    )


def text_overlay_filter(
    in_video_label: str,
    out_label: str,
    text: str,
    fontfile: str,
    font_size: int = 48,
    font_color: str = "#ffffff",
    position: str = "center",
    start_s: float = 0.0,
    end_s: float | None = None,
    opacity: float = 1.0,
    fade_in_s: float = 0.0,
    fade_out_s: float = 0.0,
) -> str:
    """Composite a text string onto a video stream via ffmpeg drawtext.

    Timing: `enable='between(t,start_s,end_s)'` gates visibility.
    Fades are expressed via the `alpha` parameter so the text fades
    rather than pops — ffmpeg evaluates the alpha expression at each
    frame and smoothly ramps 0 → opacity on fade-in, opacity → 0 on
    fade-out.

    Path-quoting: drawtext's `fontfile=` argument doesn't accept
    quotes; instead colons inside the path must be escaped (Windows
    paths like `C:\\Windows\\Fonts\\arial.ttf`). We escape colons and
    backslashes the same way drawtext expects.
    """
    if position not in _TEXT_POSITION_EXPRS:
        raise ValueError(
            f"Unknown text overlay position: {position!r}. "
            f"Known: {', '.join(sorted(_TEXT_POSITION_EXPRS))}"
        )
    x_expr, y_expr = _TEXT_POSITION_EXPRS[position]

    safe_text = _escape_drawtext(text)
    # drawtext needs the backslashes in Windows paths doubled and the
    # drive-letter colon escaped. Using forward slashes avoids the
    # backslash dance and works on Windows ffmpeg builds.
    safe_font = fontfile.replace("\\", "/").replace(":", "\\:")
    opacity = max(0.0, min(1.0, opacity))

    # Alpha expression — see docstring. Skips branches when fades
    # are zero to keep the graph readable.
    if end_s is not None and (fade_in_s > 0 or fade_out_s > 0):
        fi = max(0.001, float(fade_in_s))
        fo = max(0.001, float(fade_out_s))
        # Clamp the fade ramps inside the visible window so fades
        # don't extend before start or after end.
        alpha = (
            f"if(lt(t,{start_s:g}),0,"
            f"if(lt(t,{start_s + fi:g}),"
            f"{opacity:g}*(t-{start_s:g})/{fi:g},"
            f"if(lt(t,{end_s - fo:g}),{opacity:g},"
            f"if(lt(t,{end_s:g}),"
            f"{opacity:g}*({end_s:g}-t)/{fo:g},0))))"
        )
        alpha_clause = f":alpha='{alpha}'"
    elif opacity < 1.0:
        alpha_clause = f":alpha={opacity:g}"
    else:
        alpha_clause = ""

    enable = ""
    if end_s is not None:
        enable = f":enable='between(t,{start_s:g},{end_s:g})'"
    elif start_s > 0:
        enable = f":enable='gte(t,{start_s:g})'"

    return (
        f"[{in_video_label}]"
        f"drawtext=fontfile='{safe_font}'"
        f":text='{safe_text}'"
        f":fontcolor={font_color}"
        f":fontsize={int(font_size)}"
        f":x={x_expr}:y={y_expr}"
        f"{alpha_clause}"
        f"{enable}"
        f"[{out_label}]"
    )
