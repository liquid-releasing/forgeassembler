# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for ForgeAssembler desktop app.
#
# Build with:
#     pyinstaller ForgeAssembler.spec --clean
#
# Output:
#   Windows: dist/ForgeAssembler/ForgeAssembler.exe
#   macOS:   dist/ForgeAssembler/ForgeAssembler.app
#   Linux:   dist/ForgeAssembler/ForgeAssembler

import sys
from pathlib import Path
from PyInstaller.utils.hooks import (
    collect_all,
    collect_data_files,
    collect_submodules,
    copy_metadata,
)

SPEC_DIR = Path(SPECPATH).resolve()

# Streamlit collection (runtime-discovered dist-info, data files, etc.)
streamlit_datas, streamlit_binaries, streamlit_hiddenimports = collect_all("streamlit")
streamlit_datas += copy_metadata("streamlit")

# imageio-ffmpeg bundles a platform-specific ffmpeg binary in its package
# data dir; collect_all pulls the binary into the bundle.
ffmpeg_datas, ffmpeg_binaries, ffmpeg_hiddenimports = collect_all("imageio_ffmpeg")

# matplotlib has lots of runtime-discovered data files (font cache, mpl-data)
mpl_datas, mpl_binaries, mpl_hiddenimports = collect_all("matplotlib")

# Other packages that use importlib.metadata at runtime
extra_metadata = []
for pkg in (
    "streamlit",
    "altair",
    "pyarrow",
    "numpy",
    "pandas",
    "tornado",
    "click",
    "rich",
    "imageio-ffmpeg",
    "Pillow",
    "matplotlib",
    "requests",
):
    try:
        extra_metadata += copy_metadata(pkg)
    except Exception:
        pass

hidden_imports = (
    list(streamlit_hiddenimports)
    + list(ffmpeg_hiddenimports)
    + list(mpl_hiddenimports)
    + [
        "streamlit.web.cli",
        "streamlit.runtime.scriptrunner.magic_funcs",
        "streamlit.runtime.caching",
        "streamlit.runtime.state",
        "streamlit.components.v1",
        "altair",
        "pyarrow",
        "pydeck",
        "watchdog",
        "importlib_metadata",
        "imageio_ffmpeg",
        "PIL",
        "PIL.Image",
        "PIL.ImageDraw",
        "PIL.ImageFont",
        "numpy",
        "matplotlib",
        "matplotlib.pyplot",
        "matplotlib.backends.backend_agg",
        "requests",
        # ForgeAssembler's own packages
        "forgeassembler_core",
        "forgeassembler_core.about",
        "forgeassembler_core.chapters",
        "forgeassembler_core.concat_funscript",
        "forgeassembler_core.concat_video",
        "forgeassembler_core.debug",
        "forgeassembler_core.detect",
        "forgeassembler_core.filters",
        "forgeassembler_core.fonts",
        "forgeassembler_core.heatmap",
        "forgeassembler_core.joiners",
        "forgeassembler_core.layout",
        "forgeassembler_core.probe",
        "forgeassembler_core.project",
    ]
)

# ── Data files ─────────────────────────────────────────────────────────
datas = (
    list(streamlit_datas)
    + list(ffmpeg_datas)
    + list(mpl_datas)
    + list(extra_metadata)
)

# ForgeAssembler's own source package + UI glue
datas += [
    (str(SPEC_DIR / "forgeassembler_core"), "forgeassembler_core"),
    (str(SPEC_DIR / "ui.py"), "."),
    (str(SPEC_DIR / "media"), "media"),
    (str(SPEC_DIR / ".streamlit" / "config.toml"), ".streamlit"),
]

# License files — ship ours + the third-party list next to the exe
datas += [
    (str(SPEC_DIR / "LICENSE"), "."),
    (str(SPEC_DIR / "THIRD_PARTY_LICENSES.md"), "."),
    (str(SPEC_DIR / "README.md"), "."),
]

# Platform-specific app icon
if sys.platform == "win32":
    _icon = str(SPEC_DIR / "media" / "forgeassembler.ico")
elif sys.platform == "darwin":
    _icns = SPEC_DIR / "media" / "forgeassembler.icns"
    _icon = str(_icns) if _icns.exists() else None
else:
    _icon = None

binaries = (
    list(streamlit_binaries)
    + list(ffmpeg_binaries)
    + list(mpl_binaries)
)

block_cipher = None

a = Analysis(
    ["forgeassembler.py"],
    pathex=[str(SPEC_DIR)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "notebook",
        "jupyter",
        "IPython",
        "pytest",
        "sphinx",
        "scipy",
        "sklearn",
        "tensorflow",
        "torch",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ForgeAssembler",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ForgeAssembler",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="ForgeAssembler.app",
        icon=_icon,
        bundle_identifier="com.liquidreleasing.forgeassembler",
    )
