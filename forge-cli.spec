# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for the ForgeAssembler CLI sidecar — the Tauri app's Python
# backend. Freezes `cli.py` + `forgeassembler_core` + the bundled ffmpeg into a
# self-contained ONEDIR bundle that ships as a Tauri resource and is invoked
# once per command.
#
#   pyinstaller forge-cli.spec --clean   ->   dist/forge-cli/forge-cli(.exe)
#
# ONEDIR, not onefile: `commands.rs` calls the CLI many times per session and
# onefile re-extracts the whole payload on every call. `console=True` because
# the Rust side reads stdout.
#
# ffmpeg rides INSIDE this bundle, via imageio-ffmpeg's packaged binary —
# `concat_video._resolve_ffmpeg_exe` asks imageio_ffmpeg first and only then
# falls back to PATH. ForgeAssembler never shells ffprobe (see
# `forgeassembler_core/probe.py`: it parses ffmpeg's own stderr precisely
# because imageio-ffmpeg ships ffmpeg alone), so there is no second binary to
# source per platform.
#
# This bundle has NO Streamlit and NO pywebview: that app was retired in
# 9ecadb0, and the excludes below keep them from creeping back in through a
# transitive dependency.

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

SPEC_DIR = Path(SPECPATH).resolve()
APP_DIR = SPEC_DIR

datas, binaries, hiddenimports = [], [], []

# ── Packages with runtime-discovered data or binaries. collect_all takes
# datas + binaries + submodules in one pass, which is what these need:
# imageio_ffmpeg hides a platform-specific ffmpeg executable in its package
# data, and matplotlib carries mpl-data plus a font cache. A too-thin freeze
# fails at RUNTIME with a cryptic ImportError, so this stays broad. ──
for pkg in ("imageio_ffmpeg", "matplotlib", "numpy", "PIL"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as exc:  # noqa: BLE001 — skip anything not installed
        print(f"[forge-cli.spec] collect_all({pkg!r}) skipped: {exc}")

# The engine itself. Collected as submodules AND as a data tree: the joiner
# registry resolves its plugins by name, so a module nothing imports directly
# still has to be in the bundle.
hiddenimports += collect_submodules("forgeassembler_core")
datas += [(str(APP_DIR / "forgeassembler_core"), "forgeassembler_core")]
datas += [(str(APP_DIR / "cli.py"), ".")]

# Fonts for title cards are looked up by name at render time (`fonts.py`),
# never imported, so any bundled font files have to be carried explicitly.
_fonts = APP_DIR / "media"
if _fonts.is_dir():
    datas += [(str(_fonts), "media")]

try:
    datas += collect_data_files("matplotlib")
except Exception:  # noqa: BLE001
    pass

a = Analysis(
    ["cli.py"],
    pathex=[str(APP_DIR)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Headless backend: no GUI toolkit belongs in it, and the retired
        # Streamlit desktop app must not return through a dependency.
        "tkinter", "PyQt5", "PyQt6", "PySide2", "PySide6",
        "streamlit", "altair", "pyarrow", "pandas", "pydeck",
        "webview", "pywebview",
        "notebook", "jupyter", "IPython", "pytest", "sphinx",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="forge-cli",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,            # UPX trips antivirus false positives
    console=True,         # the Rust side reads stdout
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="forge-cli",
)
