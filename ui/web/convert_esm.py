#!/usr/bin/env python3
"""One-shot converter: rewrite the extracted global-script JSX into ESM modules.

Strategy (see migration plan): the source files were authored as classic
<script type="text/babel"> files sharing one global scope. To run them under
Vite/ESM we:
  1. keep each file's own `const { useState } = React;` destructure (works once
     React is imported as a default),
  2. prepend `import React from 'react';` (+ a supplemental hook destructure for
     any hook used but not already destructured in that file),
  3. prepend imports for cross-file symbols that are defined in exactly ONE
     other file,
  4. append an `export { ... }` for the file's own top-level symbols.

Run once from ui/web/. Idempotent-guarded by a marker comment.
"""
from __future__ import annotations
import re
from pathlib import Path

SRC = Path("src")
MARKER = "/* @esm-converted */"

# Top-level symbols defined per file (from the grep symbol map).
DEFINED = {
    "AppShell.jsx": ["FA_TABS","FA_UTILITY_TABS","FAAcceptBar","FAGlyph","FASectionLabel","FAStatusBar","FATabBody","FATabButton","FATabHeader","FATabStrip","FATopBar","fmtClipDur","fmtRelative","fmtTotal"],
    "BuildTab.jsx": ["DENSITY","AddSectionButton","AudioBedLane","AudioModeBadge","BuildTab","ChannelChip","ClipRow","ClipThumb","Divider","InlineEditor","JoinerEl","LayoutFlat","LayoutSections","LayoutTimeline","SectionHeader","StatItem"],
    "dragdrop.jsx": ["DragDropContext","DragDropProvider","DropLine","reorderClipInProject","reorderSectionInProject","useDragDrop","useDraggable","useDroppable"],
    "Inspector.jsx": ["insUseEffect","AudioPane","BedInspector","BulkTempControl","ClipInspector","ColorPane","FunscriptPane","Handle","Inspector","InspectorEmpty","MultiSelectInspector","OverlaysPane","PaneSection","SourcePane","TrimScrubber","uniq"],
    "JoinerEditor.jsx": ["AnimatedJoinerPreview","ClipPanel","computePos","JoinerEditor","makeJoinerFromKind","makeJoinerFromPreset","ParamControl","renderJoinerFrame","SavePresetPrompt","TimingVisual"],
    "MediaViewer.jsx": ["AudioWave","MediaViewer","VideoPoster"],
    "OtherTabs.jsx": ["ChapterMarkersCard","ForgePanel","ForgeTab","JoinersTab","OutputChannelsCard","OutputTab","ProjectTab","ResolutionPicker","Toggle","UserJoinerAuthor"],
    "PreviewBand.jsx": ["PreviewBand","SectionBoundaries"],
    "primitives.jsx": ["ffBtnBase","Button","Card","Field","fmtTime","fmtTimeShort","Icon","Pill","SectionHeading","Segmented","Slider","TextInput"],
    "ProjectIO.jsx": ["PIO_RECENTS","Modal","ModalFooter","OpenProjectDialog","SaveAsDialog","slug","UnsavedChangesDialog"],
    "TitleEditor.jsx": ["BUILTIN_GLYPHS","POSITION_LABEL","POSITIONS","TITLE_LAYOUTS","TITLE_THEMES","anchorFor","escapeAttr","escapeXml","findGlyph","GlyphPicker","layoutById","PositionPicker","renderGlyphSvg","renderTitleCardDataUri","renderTitleCardSvg","SaveTemplatePrompt","Section","slug","TemplateBar","TitleEditor","ToggleRow","truncate"],
    "tweaks-panel.jsx": ["__TWEAKS_STYLE","__TwkCheck","__twkIsLight","TweakButton","TweakColor","TweakNumber","TweakRadio","TweakRow","TweakSection","TweakSelect","TweakSlider","TweaksPanel","TweakText","TweakToggle","useTweaks"],
    "App.jsx": ["App","TWEAK_DEFAULTS"],
}
# data.js is special — it sets window.FA_DATA inside an IIFE.
DATA_FILE = "data.js"

HOOKS = ["useState","useEffect","useMemo","useRef","useCallback","useContext",
         "useLayoutEffect","useReducer","createContext"]

# Build symbol -> [files] index; only single-definition symbols are importable.
sym_files: dict[str, list[str]] = {}
for f, syms in DEFINED.items():
    for s in syms:
        sym_files.setdefault(s, []).append(f)
sym_files["FA_DATA"] = [DATA_FILE]
SINGLE = {s: fs[0] for s, fs in sym_files.items() if len(fs) == 1}

def destructured_hook_keys(code: str) -> set[str]:
    keys = set()
    for m in re.finditer(r"const\s*\{([^}]*)\}\s*=\s*React\s*;", code):
        for part in m.group(1).split(","):
            name = part.split(":")[0].strip()
            if name:
                keys.add(name)
    return keys

def convert(path: Path) -> None:
    code = path.read_text(encoding="utf-8")
    if code.lstrip().startswith(MARKER):
        return
    name = path.name
    own = set(DEFINED.get(name, []))

    # cross-file imports: single-def symbols referenced but not defined here
    by_file: dict[str, list[str]] = {}
    for sym, src_file in SINGLE.items():
        if src_file == name or sym in own:
            continue
        if re.search(rf"\b{re.escape(sym)}\b", code):
            by_file.setdefault(src_file, []).append(sym)

    header = [MARKER, "import React from 'react';"]

    # supplemental hooks: used but not already destructured in this file
    have = destructured_hook_keys(code)
    missing = [h for h in HOOKS if h not in have and re.search(rf"\b{h}\b", code)]
    if missing:
        header.append("const { " + ", ".join(missing) + " } = React;")

    for src_file, syms in sorted(by_file.items()):
        mod = "./" + src_file[:-4] if src_file.endswith(".jsx") else "./" + src_file[:-3]
        header.append(f"import {{ {', '.join(sorted(set(syms)))} }} from '{mod}';")

    footer = ""
    if own:
        footer = "\n\nexport { " + ", ".join(sorted(own)) + " };\n"

    path.write_text("\n".join(header) + "\n\n" + code + footer, encoding="utf-8")
    print(f"{name}: +{sum(len(v) for v in by_file.values())} imports, "
          f"{len(own)} exports, hooks+={missing}")

def convert_data(path: Path) -> None:
    code = path.read_text(encoding="utf-8")
    if code.lstrip().startswith(MARKER):
        return
    # IIFE already assigns window.FA_DATA; re-export it for ESM consumers.
    path.write_text(
        MARKER + "\n" + code + "\n\nexport const FA_DATA = window.FA_DATA;\n",
        encoding="utf-8",
    )
    print("data.js: exported FA_DATA")

for jsx in sorted(SRC.glob("*.jsx")):
    convert(jsx)
convert_data(SRC / DATA_FILE)
print("done")
