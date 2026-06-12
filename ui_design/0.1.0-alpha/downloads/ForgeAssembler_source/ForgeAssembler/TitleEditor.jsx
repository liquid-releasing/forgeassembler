// TitleEditor — modal for authoring a title.
//
// Two output paths (chosen via "Use as" toggle at the top):
//
//   • Standalone segment — a still-image segment that takes its own
//     slot in the timeline. You pick the insertion point relative
//     to the currently-selected clip (before / after / end of section).
//
//   • Overlay on a clip — a transparent-background image overlay
//     pushed onto the selected clip's `overlays` array, with its
//     own start time, fade in, fade out, and opacity.
//
// The renderer is shared. `transparent: true` skips the background
// rect so the same layout can be composited over a video frame.

const { useState: teState, useMemo: teMemo, useEffect: teUseEffect, useRef: teRef } = React;

// ── Layouts ──────────────────────────────────────────────────────
// `natural` = which 3×3 cell this layout sits in by default in overlay
//             mode. The user can override via the position picker.
// `size`    = the layout's natural content bounding box (% of frame)
//             when rendered as an overlay. Wider, shorter for
//             lower-third-style treatments; smaller for hero blocks.
const TITLE_LAYOUTS = [
  { id: "centered",   label: "Centered hero",   sub: "Big title.",
    natural: "center", size: [0.65, 0.45] },
  { id: "chapter",    label: "Chapter plate",   sub: "Eyebrow + title.",
    natural: "ml",     size: [0.65, 0.45] },
  { id: "lower",      label: "Lower third",     sub: "Title strip.",
    natural: "bl",     size: [0.92, 0.32] },
  { id: "fullquote",  label: "Full quote",      sub: "Type fills frame.",
    natural: "center", size: [0.85, 0.65] },
];

// Position grid — 9 cells. All visible in overlay mode.
const POSITIONS = [
  ["tl", "tc", "tr"],
  ["ml", "center", "mr"],
  ["bl", "bc", "br"],
];
const POSITION_LABEL = {
  tl: "Top left",    tc: "Top center",    tr: "Top right",
  ml: "Middle left", center: "Center",    mr: "Middle right",
  bl: "Bottom left", bc: "Bottom center", br: "Bottom right",
};

function layoutById(id) { return TITLE_LAYOUTS.find(L => L.id === id) || TITLE_LAYOUTS[0]; }

// ── Glyph library ────────────────────────────────────────────────
// Built-in forge-themed glyphs. `paths` is rendered into an SVG <g>
// at the glyph's anchor with a uniform scale factor `s`. Coordinates
// are in a centered [-1, 1] space; the renderer multiplies by `s`.
// User-added glyphs come in as data URIs (via the upload picker) and
// are rendered as <image> elements instead.
const BUILTIN_GLYPHS = [
  { id: "none",   label: "None",   builtin: true, kind: "none" },
  { id: "anvil",  label: "Anvil",  builtin: true, kind: "path",
    paths: [
      "M -0.60 0.45 L 0.60 0.45 L 0.45 0.65 L -0.45 0.65 Z",
      "M -0.42 -0.12 L 0.55 -0.12 L 0.42 0.18 L -0.30 0.18 Z",
      "M -0.50 -0.12 L -0.30 0.18 L -0.55 0.45 L -0.70 0.45 L -0.70 -0.12 Z",
    ] },
  { id: "hammer", label: "Hammer", builtin: true, kind: "path",
    paths: [
      "M -0.50 -0.45 L 0.50 -0.45 L 0.50 -0.05 L -0.50 -0.05 Z",
      "M -0.08 -0.05 L 0.08 -0.05 L 0.05 0.65 L -0.05 0.65 Z",
    ] },
  { id: "tongs",  label: "Tongs",  builtin: true, kind: "path",
    paths: [
      "M -0.55 0.55 Q -0.65 0.0 -0.20 -0.30 L -0.10 -0.20 Q -0.45 0.10 -0.30 0.55 Z",
      "M 0.55 0.55 Q 0.65 0.0 0.20 -0.30 L 0.10 -0.20 Q 0.45 0.10 0.30 0.55 Z",
      "M -0.10 -0.20 L 0.10 -0.20 L 0.10 -0.55 L -0.10 -0.55 Z",
    ] },
  { id: "oven",   label: "Oven",   builtin: true, kind: "path",
    paths: [
      "M -0.60 -0.50 L 0.60 -0.50 L 0.60 0.55 L -0.60 0.55 Z",
      "M -0.35 -0.20 L 0.35 -0.20 L 0.35 0.30 L -0.35 0.30 Z",
      "M -0.50 -0.55 L 0.50 -0.55 L 0.45 -0.65 L -0.45 -0.65 Z",
    ] },
  { id: "spark",  label: "Spark",  builtin: true, kind: "path",
    paths: [
      "M 0 -0.65 L 0.10 -0.10 L 0.65 0 L 0.10 0.10 L 0 0.65 L -0.10 0.10 L -0.65 0 L -0.10 -0.10 Z",
    ] },
  { id: "circle", label: "Dot",    builtin: true, kind: "path",
    paths: ["M -0.30 0 A 0.30 0.30 0 1 0 0.30 0 A 0.30 0.30 0 1 0 -0.30 0 Z"] },
];

function findGlyph(id, userGlyphs = []) {
  return BUILTIN_GLYPHS.find(g => g.id === id) || userGlyphs.find(g => g.id === id) || BUILTIN_GLYPHS[0];
}

// Renders a glyph as an SVG fragment, anchored at (cx, cy) with `size`
// being the half-width of its [-1..1] coordinate space.
function renderGlyphSvg(g, cx, cy, size, color) {
  if (!g || g.kind === "none") return "";
  if (g.kind === "image") {
    const half = size;
    return `<image href="${escapeAttr(g.dataUri)}" x="${cx - half}" y="${cy - half}" width="${half * 2}" height="${half * 2}" preserveAspectRatio="xMidYMid meet" />`;
  }
  return `<g transform="translate(${cx} ${cy}) scale(${size})" fill="${color}">${g.paths.map(p => `<path d="${p}" />`).join("")}</g>`;
}
function escapeAttr(s) { return String(s).replace(/"/g, "&quot;"); }

// Compute where (x,y) the content box sits inside the W×H frame for
// the chosen position, with a margin from the edges.
function anchorFor(pos, W, H, bW, bH, mW, mH) {
  const isTop    = pos.startsWith("t");
  const isBottom = pos.startsWith("b");
  const isLeft   = pos.endsWith("l");
  const isRight  = pos.endsWith("r");
  const x = isLeft ? mW : (isRight ? W - bW - mW : (W - bW) / 2);
  const y = isTop  ? mH : (isBottom ? H - bH - mH : (H - bH) / 2);
  return { x, y };
}

const TITLE_THEMES = [
  { id: "dark",   bg: "#0e1117", fg: "#fafafa", accent: "#ff4b4b" },
  { id: "void",   bg: "#000000", fg: "#fafafa", accent: "#ff8c42" },
  { id: "brand",  bg: "#1a0e1e", fg: "#fafafa", accent: "#ff4b4b" },
  { id: "light",  bg: "#fafafa", fg: "#0e1117", accent: "#ff4b4b" },
];

// ── SVG renderer ─────────────────────────────────────────────────
// `transparent` controls whether we paint the background rect.
// `overlayPosition` (optional) — when set in overlay mode, wraps the
// layout's drawing in a translate+scale so it sits inside the chosen
// cell of the 3×3 anchor grid.
function renderTitleCardSvg(t, { width = 320, height = 180, transparent = false, userGlyphs = [] } = {}) {
  const W = width, H = height;
  const theme = TITLE_THEMES.find(th => th.id === t.theme) || TITLE_THEMES[0];
  const k = H / 1080;
  const layout = t.layout;

  const titleStr = (t.title || "").trim();
  const subStr = (t.subtitle || "").trim();
  const eyebrowStr = (t.eyebrow || "").trim();

  function txt(x, y, str, size, weight, color, anchor = "start", letterSpacing = "0") {
    return `<text x="${x}" y="${y}" font-family="Inter,system-ui,-apple-system,sans-serif" font-size="${size}" font-weight="${weight}" fill="${color}" text-anchor="${anchor}" letter-spacing="${letterSpacing}">${escapeXml(str)}</text>`;
  }
  function rect(x, y, w, h, color, op = 1) {
    return `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${color}" opacity="${op}" />`;
  }
  function glyph(cx, cy, size, color) {
    const g = findGlyph(t.glyph ?? (t.showGlyph ? "anvil" : "none"), userGlyphs);
    return renderGlyphSvg(g, cx, cy, size, color);
  }

  let inner = "";
  if (!transparent) inner += rect(0, 0, W, H, theme.bg);

  if (layout === "centered") {
    if ((t.glyph ?? (t.showGlyph ? "anvil" : "none")) !== "none") {
      inner += glyph(W * 0.5, H * 0.30, k * 110, theme.accent);
    }
    const titleSize = k * 130;
    const titleY    = H * 0.55;
    if (titleStr) inner += txt(W * 0.5, titleY, titleStr, titleSize, 800, theme.fg, "middle", "-0.025em");
    if (subStr)   inner += txt(W * 0.5, titleY + titleSize * 0.85, subStr, k * 36, 500, theme.fg + "B3", "middle", "0.04em");
    inner += `<line x1="${W*0.42}" x2="${W*0.58}" y1="${H*0.78}" y2="${H*0.78}" stroke="${theme.accent}" stroke-width="${Math.max(1, k*4)}"/>`;
  }
  else if (layout === "chapter") {
    inner += rect(W * 0.10, H * 0.35, k * 6, H * 0.30, theme.accent);
    const eyebrowY = H * 0.42;
    inner += txt(W * 0.13, eyebrowY, (eyebrowStr || "CHAPTER").toUpperCase(), k * 28, 700, theme.accent, "start", "0.18em");
    if (titleStr) inner += txt(W * 0.13, H * 0.58, titleStr, k * 110, 700, theme.fg, "start", "-0.02em");
    if (subStr)   inner += txt(W * 0.13, H * 0.68, subStr, k * 32, 500, theme.fg + "B3", "start", "0");
  }
  else if (layout === "lower") {
    inner += `<defs><linearGradient id="lg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#000" stop-opacity="0"/>
      <stop offset="1" stop-color="#000" stop-opacity="${transparent ? 0.7 : 1}"/></linearGradient></defs>`;
    inner += rect(0, H * 0.55, W, H * 0.45, "url(#lg)");
    inner += rect(W * 0.08, H * 0.75, k * 6, H * 0.14, theme.accent);
    if (titleStr) inner += txt(W * 0.10, H * 0.85, titleStr, k * 76, 700, "#fafafa", "start", "-0.01em");
    if (subStr)   inner += txt(W * 0.10, H * 0.91, subStr, k * 28, 500, "#fafafaB3", "start", "0.02em");
  }
  else if (layout === "fullquote") {
    if (transparent) {
      inner += rect(0, 0, W, H, "#000", 0.4);
    }
    if (titleStr) {
      const words = titleStr.split(/\s+/);
      const lines = [];
      let cur = "";
      const maxLen = Math.max(8, Math.floor(W / (k * 48)));
      for (const w of words) {
        if ((cur + " " + w).trim().length > maxLen) { if (cur) lines.push(cur); cur = w; }
        else cur = (cur + " " + w).trim();
      }
      if (cur) lines.push(cur);
      const lh = k * 110;
      const startY = H * 0.5 - ((lines.length - 1) * lh) / 2;
      const fg = transparent ? "#fafafa" : theme.fg;
      lines.forEach((ln, i) => {
        inner += txt(W * 0.5, startY + i * lh, ln, k * 96, 800, fg, "middle", "-0.025em");
      });
    }
    const subFg = transparent ? "#fafafa99" : theme.fg + "99";
    inner += txt(W * 0.5, H * 0.92, "— " + (subStr || "anonymous").toLowerCase(), k * 32, 500, subFg, "middle", "0.04em");
  }

  // ── Overlay positioning ────────────────────────────────────────
  // When in overlay mode AND a position is specified, fit the
  // full-frame drawing into a smaller anchored box.
  if (transparent && t.overlayPosition) {
    const L = layoutById(layout);
    const naturalW = (L.size?.[0] ?? 0.7) * W;
    const naturalH = (L.size?.[1] ?? 0.5) * H;
    const margin = Math.min(W, H) * 0.045;
    const a = anchorFor(t.overlayPosition, W, H, naturalW, naturalH, margin, margin);
    const sx = naturalW / W;
    const sy = naturalH / H;
    inner = `<g transform="translate(${a.x},${a.y}) scale(${sx},${sy})">${inner}</g>`;
  }

  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid slice">${inner}</svg>`;
}
function escapeXml(s) {
  return s.replace(/[<>&"']/g, (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", "\"": "&quot;", "'": "&apos;" }[c]));
}
function renderTitleCardDataUri(t, opts) {
  const svg = renderTitleCardSvg(t, opts);
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

// ── TitleEditor ─────────────────────────────────────────────────
function TitleEditor({ initial, selectedSeg, userGlyphs = [], userTemplates = [],
                        onAddUserGlyph, onAddUserTemplate, onCancel, onSave }) {
  const [draft, setDraft] = teState(() => {
    const initLayout = (initial?.layout) || "centered";
    return {
      layout: initLayout,
      theme: "dark",
      title: "Chapter one",
      eyebrow: "Act I",
      subtitle: "Tender, slow build",
      glyph: "anvil",
      durationS: 4.5,
      // overlay path
      overlayStartS: 0.5,
      overlayFadeInS: 0.6,
      overlayFadeOutS: 0.6,
      overlayOpacity: 1.0,
      overlayPosition: layoutById(initLayout).natural,
      // mode + insertion
      useAs: selectedSeg ? "overlay" : "standalone",
      insertionPoint: selectedSeg ? "after" : "end", // before | after | end
      ...(initial || {}),
    };
  });
  function set(k, v) {
    setDraft(d => {
      const next = { ...d, [k]: v };
      // Layout change → reset position to the new layout's natural anchor.
      if (k === "layout" && d.overlayPosition === layoutById(d.layout).natural) {
        next.overlayPosition = layoutById(v).natural;
      }
      return next;
    });
  }

  // Disable "overlay" path if no clip is selected — only standalone has meaning.
  const overlayAvailable = !!selectedSeg;
  // If a clip is selected and is a still itself, overlay-on-still is weird; allow but warn.

  // Lock useAs to standalone if no clip selected.
  teUseEffect(() => {
    if (!overlayAvailable && draft.useAs === "overlay") set("useAs", "standalone");
  }, [overlayAvailable]);

  const [savingTemplate, setSavingTemplate] = teState(false);

  // Live preview SVG — transparent in overlay mode so it composites
  // over the selected clip's thumbnail. Position is honoured when set.
  const isOverlay = draft.useAs === "overlay" && overlayAvailable;
  const svg = teMemo(() =>
    renderTitleCardSvg(draft, { width: 1920, height: 1080, transparent: isOverlay, userGlyphs }),
    [draft, isOverlay, userGlyphs]);

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 40, background: "rgba(0,0,0,0.65)",
      display: "grid", placeItems: "center",
    }} onClick={onCancel}>
      <div onClick={(e) => e.stopPropagation()} style={{
        width: 1020, maxHeight: "92vh", overflow: "hidden",
        display: "flex", flexDirection: "column",
        background: "var(--surface)", border: "1px solid var(--border)",
        borderRadius: 12, boxShadow: "var(--elev-3)",
      }}>
        {/* Header */}
        <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--border)",
                       display: "flex", alignItems: "center", gap: 10 }}>
          <Icon name="type" size={16} style={{ color: "var(--accent-warm)" }} />
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 14, fontWeight: 600 }}>Title</div>
            <div style={{ fontSize: 11, color: "var(--text-dim)" }}>
              Author it once. Drop it in as a standalone segment, or overlay it on a clip.
            </div>
          </div>
          <Button kind="ghost" size="icon" onClick={onCancel}><Icon name="x" size={14} /></Button>
        </div>

        {/* Use-as toggle */}
        <div style={{ padding: "12px 18px", borderBottom: "1px solid var(--border)",
                       display: "flex", alignItems: "center", gap: 14 }}>
          <span style={{ fontSize: 10.5, fontWeight: 700, color: "var(--text-dim)",
                          textTransform: "uppercase", letterSpacing: "0.1em" }}>Use as</span>
          <Segmented value={draft.useAs}
                      onChange={(v) => set("useAs", v)}
                      options={[
                        { value: "standalone", label: "Standalone segment" },
                        { value: "overlay",    label: overlayAvailable
                                                  ? `Overlay on “${truncate(selectedSeg.title, 24)}”`
                                                  : "Overlay (select a clip first)" },
                      ]} />
          {!overlayAvailable && draft.useAs === "overlay" && (
            <Pill tone="warn" style={{ fontSize: 10 }}>no clip selected</Pill>
          )}
          <div style={{ flex: 1 }} />
          <span style={{ fontSize: 11, color: "var(--text-muted)", maxWidth: 320, textAlign: "right", lineHeight: 1.4 }}>
            {draft.useAs === "standalone"
              ? "Becomes its own still-image segment. Holds for the duration you set."
              : "Rendered as a transparent PNG that fades in over the selected clip, then fades out."}
          </span>
        </div>

        {/* Templates bar — built-in layouts + user-saved templates */}
        <div style={{ padding: "10px 14px", borderBottom: "1px solid var(--border)",
                       background: "var(--surface-2)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
            <span style={{ fontSize: 10.5, fontWeight: 700, color: "var(--text-dim)",
                            textTransform: "uppercase", letterSpacing: "0.1em" }}>Templates</span>
            <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
              Click any to load. Save the current title with the button at the bottom.
            </span>
          </div>
          <TemplateBar value={draft}
                        userTemplates={userTemplates}
                        userGlyphs={userGlyphs}
                        onLoad={(tDraft) => setDraft(d => ({ ...d, ...tDraft }))} />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr",
                       flex: 1, minHeight: 0 }}>
          {/* Live preview + layout picker */}
          <div style={{
            background: "var(--bg)", padding: 18, display: "flex",
            flexDirection: "column", gap: 12, minHeight: 0, overflow: "auto",
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 10.5, fontWeight: 700, color: "var(--text-dim)",
                              textTransform: "uppercase", letterSpacing: "0.1em" }}>Preview</span>
              <span className="mono" style={{ fontSize: 10.5, color: "var(--text-dim)" }}>
                1920 × 1080 ·{" "}
                {isOverlay
                  ? `${draft.overlayFadeInS}s in · ${draft.overlayFadeOutS}s out · @${Math.round(draft.overlayOpacity * 100)}%`
                  : `${draft.durationS.toFixed(1)}s`}
              </span>
              <div style={{ flex: 1 }} />
              <span className="mono" style={{ fontSize: 10.5, color: "var(--text-dim)" }}>
                output: {isOverlay
                  ? `overlay-${slug(draft.title)}.png`
                  : `title-${slug(draft.title)}.png`}
              </span>
            </div>

            {/* Frame */}
            <div style={{
              aspectRatio: "16 / 9", width: "100%", position: "relative",
              background: "#000", border: "1px solid var(--border)", borderRadius: 6,
              overflow: "hidden",
            }}>
              {isOverlay && selectedSeg && (
                <img src={selectedSeg.thumb} alt="" style={{
                  position: "absolute", inset: 0, width: "100%", height: "100%",
                  objectFit: "cover",
                }} />
              )}
              <div style={{
                position: "absolute", inset: 0, opacity: isOverlay ? draft.overlayOpacity : 1,
              }} dangerouslySetInnerHTML={{ __html: svg }} />
            </div>

            {/* Layout grid */}
            <span style={{ fontSize: 10.5, fontWeight: 700, color: "var(--text-dim)",
                             textTransform: "uppercase", letterSpacing: "0.1em" }}>Layout</span>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8 }}>
              {TITLE_LAYOUTS.map(L => {
                const active = draft.layout === L.id;
                const thumb = renderTitleCardSvg({ ...draft, layout: L.id }, { width: 240, height: 135, transparent: isOverlay });
                return (
                  <button key={L.id} onClick={() => set("layout", L.id)} style={{
                    display: "flex", flexDirection: "column", gap: 5,
                    padding: 6, borderRadius: 6,
                    background: active ? "rgba(255,75,75,0.06)" : "var(--surface)",
                    border: `1px solid ${active ? "var(--accent)" : "var(--border)"}`,
                    cursor: "pointer", textAlign: "left", color: "var(--text)",
                    fontFamily: "inherit",
                  }}>
                    <div style={{
                      aspectRatio: "16 / 9", borderRadius: 3, overflow: "hidden",
                      border: "1px solid var(--border)", position: "relative",
                      background: isOverlay && selectedSeg ? `url(${selectedSeg.thumb}) center/cover` : "#000",
                    }}>
                      <div style={{ position: "absolute", inset: 0 }}
                            dangerouslySetInnerHTML={{ __html: thumb }} />
                    </div>
                    <span style={{ fontSize: 11, fontWeight: 600 }}>{L.label}</span>
                    <span style={{ fontSize: 10, color: "var(--text-dim)", lineHeight: 1.4 }}>{L.sub}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Right: controls */}
          <div style={{ padding: 18, borderLeft: "1px solid var(--border)",
                         minHeight: 0, overflow: "auto",
                         display: "flex", flexDirection: "column", gap: 16 }}>
            <Section label="Type">
              {draft.layout === "chapter" && (
                <Field label="Eyebrow"><TextInput value={draft.eyebrow}
                                                    onChange={(v) => set("eyebrow", v)}
                                                    placeholder="ACT I" /></Field>
              )}
              <Field label={draft.layout === "fullquote" ? "Quote" : "Title"}>
                <TextInput value={draft.title} onChange={(v) => set("title", v)}
                            placeholder="Chapter one" />
              </Field>
              <Field label={draft.layout === "fullquote" ? "Attribution" : "Subtitle"}>
                <TextInput value={draft.subtitle} onChange={(v) => set("subtitle", v)}
                            placeholder={draft.layout === "fullquote" ? "anonymous" : "optional"} />
              </Field>
            </Section>

            <Section label="Theme">
              <div style={{ display: "flex", gap: 6 }}>
                {TITLE_THEMES.map(th => {
                  const active = draft.theme === th.id;
                  return (
                    <button key={th.id} onClick={() => set("theme", th.id)}
                              title={th.id}
                              style={{
                                flex: 1, height: 40, borderRadius: 6,
                                position: "relative", cursor: "pointer",
                                background: th.bg,
                                border: `1px solid ${active ? "var(--accent)" : "var(--border)"}`,
                                boxShadow: active ? "0 0 0 1px rgba(255,75,75,0.3)" : "none",
                              }}>
                      <span style={{
                        position: "absolute", inset: 6, borderRadius: 3,
                        display: "grid", gridTemplateColumns: "1fr 14px", gap: 4,
                        alignItems: "center", justifyItems: "stretch",
                      }}>
                        <span style={{ height: 3, borderRadius: 1, background: th.fg, opacity: 0.85 }} />
                        <span style={{ width: 12, height: 12, borderRadius: 2, background: th.accent }} />
                      </span>
                    </button>
                  );
                })}
              </div>
              {isOverlay && (
                <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 6, lineHeight: 1.45 }}>
                  In overlay mode the theme background is replaced by your clip —
                  only the type, accent, and (for lower-third / full-quote) the
                  legibility scrim are baked in.
                </div>
              )}
            </Section>

            <Section label="Brand glyph">
              <GlyphPicker value={draft.glyph}
                            userGlyphs={userGlyphs}
                            onChange={(v) => set("glyph", v)}
                            onAddUserGlyph={onAddUserGlyph} />
            </Section>

            {/* Mode-specific controls */}
            {draft.useAs === "standalone" ? (
              <>
                <Section label="Hold duration">
                  <Slider value={draft.durationS} min={1.0} max={15} step={0.5}
                          onChange={(v) => set("durationS", v)}
                          valueLabel={`${draft.durationS.toFixed(1)}s`} />
                </Section>
                <Section label="Insertion point">
                  <Segmented value={draft.insertionPoint}
                              onChange={(v) => set("insertionPoint", v)}
                              options={selectedSeg
                                ? [
                                    { value: "before", label: "Before clip" },
                                    { value: "after",  label: "After clip"  },
                                    { value: "end",    label: "End of section" },
                                  ]
                                : [{ value: "end", label: "End of section" }]} />
                  <div style={{ marginTop: 6, fontSize: 11, color: "var(--text-dim)", lineHeight: 1.45 }}>
                    {selectedSeg
                      ? <>Inserts {draft.insertionPoint === "end" ? "at the end of the section that contains" : draft.insertionPoint}{" "}
                          <strong style={{ color: "var(--text-muted)" }}>{selectedSeg.title}</strong>.</>
                      : "No clip selected — the new segment lands at the end of the last section."}
                  </div>
                </Section>
              </>
            ) : (
              <>
                <Section label="Position on clip">
                  <PositionPicker value={draft.overlayPosition}
                                    onChange={(v) => set("overlayPosition", v)}
                                    natural={layoutById(draft.layout).natural} />
                </Section>
                <Section label="Timing on clip">
                  <Slider value={draft.overlayStartS} min={0} max={Math.max(2, (selectedSeg?.durMs || 0) / 1000)}
                          step={0.1} onChange={(v) => set("overlayStartS", v)}
                          label="Start at"
                          valueLabel={`${draft.overlayStartS.toFixed(1)}s into clip`} />
                  <Slider value={draft.overlayFadeInS} min={0} max={5} step={0.1}
                          onChange={(v) => set("overlayFadeInS", v)}
                          label="Fade in"
                          valueLabel={`${draft.overlayFadeInS.toFixed(1)}s`} />
                  <Slider value={draft.overlayFadeOutS} min={0} max={5} step={0.1}
                          onChange={(v) => set("overlayFadeOutS", v)}
                          label="Fade out"
                          valueLabel={`${draft.overlayFadeOutS.toFixed(1)}s`} />
                  <Slider value={draft.overlayOpacity * 100} min={20} max={100} step={5}
                          onChange={(v) => set("overlayOpacity", v / 100)}
                          label="Opacity"
                          valueLabel={`${Math.round(draft.overlayOpacity * 100)}%`} />
                </Section>
              </>
            )}
          </div>
        </div>

        {/* Footer */}
        <div style={{ padding: "12px 18px", borderTop: "1px solid var(--border)",
                       display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <Button kind="ghost" size="sm" icon="bookmark-plus"
                   onClick={() => setSavingTemplate(true)}
                   style={{ marginRight: "auto" }}>Save as template…</Button>
          <Button kind="ghost" size="sm" onClick={onCancel}>Cancel</Button>
          <Button kind="primary" size="sm" icon="check"
                  onClick={() => {
                    const layout = layoutById(draft.layout);
                    const forSave = { ...draft };
                    forSave.overlayPosition = forSave.overlayPosition || layout.natural;
                    const standalone = renderTitleCardDataUri(forSave, { width: 320, height: 180, transparent: false, userGlyphs });
                    const transparent = renderTitleCardDataUri(forSave, { width: 320, height: 180, transparent: true, userGlyphs });
                    onSave({
                      ...forSave,
                      thumb: draft.useAs === "overlay" ? transparent : standalone,
                      overlayThumb: transparent,
                    });
                  }}>
            {draft.useAs === "overlay" ? "Add overlay" : "Add segment"}
          </Button>
        </div>
      </div>

      {savingTemplate && (
        <SaveTemplatePrompt draft={draft}
                              onCancel={() => setSavingTemplate(false)}
                              onSave={(name) => {
                                const id = `ut-${Date.now()}`;
                                onAddUserTemplate?.({
                                  id, name, builtin: false,
                                  draft: {
                                    layout: draft.layout, theme: draft.theme,
                                    glyph: draft.glyph, overlayPosition: draft.overlayPosition,
                                  },
                                });
                                setSavingTemplate(false);
                              }} />
      )}
    </div>
  );
}

// ── Position picker (3×3 grid) ───────────────────────────────────
function PositionPicker({ value, onChange, natural }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{
        display: "grid", gridTemplateColumns: "repeat(3, 40px)",
        gridTemplateRows: "repeat(3, 28px)", gap: 4,
        background: "var(--surface-2)", border: "1px solid var(--border)",
        borderRadius: 6, padding: 6, width: "max-content",
      }}>
        {POSITIONS.flat().map((pos) => {
          const active = value === pos;
          const isNatural = natural === pos;
          return (
            <button key={pos} onClick={() => onChange(pos)}
                     title={POSITION_LABEL[pos] + (isNatural ? " (layout default)" : "")}
                     style={{
                       borderRadius: 4, padding: 0, cursor: "pointer",
                       background: active ? "var(--accent)" : "transparent",
                       border: `1px solid ${active ? "var(--accent)" : "var(--border)"}`,
                       display: "grid", placeItems: "center",
                     }}>
              <span style={{
                width: 7, height: 7, borderRadius: "50%",
                background: active ? "#fff"
                  : (isNatural ? "var(--accent-warm)" : "var(--text-dim)"),
                opacity: active ? 1 : 0.8,
              }} />
            </button>
          );
        })}
      </div>
      <div style={{ fontSize: 11.5, color: "var(--text-muted)", lineHeight: 1.45 }}>
        {POSITION_LABEL[value]}
        {natural === value && (
          <span style={{ color: "var(--text-dim)", marginLeft: 6 }}>· layout default</span>
        )}
      </div>
    </div>
  );
}

// ── Glyph picker ────────────────────────────────────────────────
function GlyphPicker({ value, userGlyphs = [], onChange, onAddUserGlyph }) {
  const fileRef = teRef();
  const all = [...BUILTIN_GLYPHS, ...userGlyphs];

  function pickFile() { fileRef.current?.click(); }
  function onFileChange(e) {
    const f = e.target.files?.[0];
    if (!f) return;
    const reader = new FileReader();
    reader.onload = () => {
      const id = `ug-${Date.now()}`;
      onAddUserGlyph?.({
        id, label: f.name.replace(/\.[^.]+$/, ""),
        kind: "image", builtin: false,
        dataUri: String(reader.result),
      });
      onChange?.(id);
    };
    reader.readAsDataURL(f);
    e.target.value = "";
  }

  return (
    <>
      <input ref={fileRef} type="file" accept="image/svg+xml,image/png"
              onChange={onFileChange} style={{ display: "none" }} />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 4 }}>
        {all.map(g => {
          const active = value === g.id;
          return (
            <button key={g.id} onClick={() => onChange?.(g.id)}
                     title={g.label + (g.builtin ? "" : " · custom")}
                     style={{
                       aspectRatio: "1", padding: 6, cursor: "pointer",
                       background: active ? "rgba(255,75,75,0.08)" : "var(--surface-2)",
                       border: `1px solid ${active ? "var(--accent)" : "var(--border)"}`,
                       borderRadius: 5, position: "relative",
                       display: "grid", placeItems: "center",
                     }}>
              {g.kind === "none"
                ? <span className="mono" style={{ fontSize: 10, color: "var(--text-dim)" }}>—</span>
                : (g.kind === "image"
                    ? <img src={g.dataUri} alt="" style={{ width: "70%", height: "70%", objectFit: "contain" }} />
                    : <svg viewBox="-1 -1 2 2" width="60%" height="60%">
                        {g.paths.map((d, i) => (
                          <path key={i} d={d} fill={active ? "var(--accent)" : "var(--text)"} />
                        ))}
                      </svg>)}
              {!g.builtin && (
                <span style={{
                  position: "absolute", top: 2, right: 3,
                  fontFamily: "var(--font-mono)", fontSize: 8, fontWeight: 700,
                  color: "var(--accent-warm)", letterSpacing: "0.04em",
                  textTransform: "uppercase",
                }}>custom</span>
              )}
            </button>
          );
        })}
        <button onClick={pickFile} title="Add a custom glyph (SVG or PNG)"
                style={{
                  aspectRatio: "1", padding: 6, cursor: "pointer",
                  background: "transparent",
                  border: "1px dashed var(--border-strong)",
                  borderRadius: 5, color: "var(--text-muted)",
                  display: "flex", flexDirection: "column", gap: 2,
                  alignItems: "center", justifyContent: "center",
                  fontFamily: "inherit", fontSize: 9.5, fontWeight: 600,
                }}>
          <Icon name="plus" size={14} />
          custom
        </button>
      </div>
      <div style={{ marginTop: 6, fontSize: 10.5, color: "var(--text-dim)", lineHeight: 1.4 }}>
        SVG renders sharpest. PNG works but won't scale cleanly at 4K.
      </div>
    </>
  );
}

// ── Template bar ─────────────────────────────────────────────────
// Built-in templates are the 4 layouts. User templates are saved
// drafts. Click any to load it into the editor.
function TemplateBar({ value, userTemplates = [], userGlyphs = [], onLoad }) {
  const builtin = TITLE_LAYOUTS.map(L => ({
    id: `builtin:${L.id}`,
    name: L.label,
    builtin: true,
    draft: { layout: L.id, theme: "dark", title: "Title", subtitle: "Subtitle",
              eyebrow: "ACT", glyph: "anvil", overlayPosition: L.natural },
  }));
  const all = [...builtin, ...userTemplates.map(t => ({ ...t, builtin: false }))];
  return (
    <div style={{ display: "flex", gap: 8, overflowX: "auto", padding: "2px 0 4px" }}>
      {all.map(t => {
        const thumb = renderTitleCardSvg(t.draft, { width: 240, height: 135, userGlyphs });
        const active = value && t.draft && value.layout === t.draft.layout && value.glyph === t.draft.glyph
                        && value.theme === t.draft.theme;
        return (
          <button key={t.id} onClick={() => onLoad?.(t.draft)}
                   title={t.name + (t.builtin ? "" : " · custom")}
                   style={{
                     flex: "0 0 auto", width: 132, padding: 5, cursor: "pointer",
                     background: active ? "rgba(255,75,75,0.06)" : "var(--surface)",
                     border: `1px solid ${active ? "var(--accent)" : "var(--border)"}`,
                     borderRadius: 6, color: "var(--text)",
                     fontFamily: "inherit", textAlign: "left",
                     display: "flex", flexDirection: "column", gap: 4,
                     position: "relative",
                   }}>
            <div style={{ aspectRatio: "16 / 9", borderRadius: 3, overflow: "hidden",
                            border: "1px solid var(--border)" }}
                  dangerouslySetInnerHTML={{ __html: thumb }} />
            <span style={{ fontSize: 11, fontWeight: 600,
                             overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {t.name}
            </span>
            {!t.builtin && (
              <span style={{
                position: "absolute", top: 5, right: 5,
                fontFamily: "var(--font-mono)", fontSize: 8, fontWeight: 700,
                color: "#fff", background: "rgba(255,140,66,0.85)",
                letterSpacing: "0.05em", textTransform: "uppercase",
                padding: "1px 4px", borderRadius: 2,
              }}>saved</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

// ── Save-as-template prompt ─────────────────────────────────────
function SaveTemplatePrompt({ draft, onCancel, onSave }) {
  const [name, setName] = teState(`${draft.title || "Untitled"} · ${layoutById(draft.layout).label.toLowerCase()}`);
  return (
    <div onClick={onCancel} style={{
      position: "fixed", inset: 0, zIndex: 50,
      background: "rgba(0,0,0,0.65)", display: "grid", placeItems: "center",
    }}>
      <div onClick={(e) => e.stopPropagation()} style={{
        width: 420, background: "var(--surface)",
        border: "1px solid var(--border)", borderRadius: 10,
        boxShadow: "var(--elev-3)", padding: 18,
        display: "flex", flexDirection: "column", gap: 14,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Icon name="bookmark-plus" size={16} style={{ color: "var(--accent-warm)" }} />
          <span style={{ fontSize: 14, fontWeight: 600 }}>Save title as template</span>
        </div>
        <div style={{ fontSize: 11.5, color: "var(--text-muted)", lineHeight: 1.5 }}>
          Saves the current layout, theme, glyph, and overlay position as a reusable
          template. The body text isn't saved — only the styling.
        </div>
        <Field label="Template name"><TextInput value={name} onChange={setName} /></Field>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <Button kind="ghost" size="sm" onClick={onCancel}>Cancel</Button>
          <Button kind="primary" size="sm" disabled={!name.trim()}
                   onClick={() => onSave(name.trim())}>Save template</Button>
        </div>
      </div>
    </div>
  );
}

// Helpers
function Section({ label, children }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <span style={{ fontSize: 10.5, fontWeight: 700, color: "var(--text-dim)",
                      textTransform: "uppercase", letterSpacing: "0.1em" }}>{label}</span>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>{children}</div>
    </div>
  );
}
function ToggleRow({ label, checked, onChange }) {
  return (
    <button onClick={() => onChange(!checked)} style={{
      display: "flex", alignItems: "center", gap: 10, width: "100%",
      padding: 0, background: "transparent", border: "none",
      cursor: "pointer", textAlign: "left", color: "var(--text)",
      fontFamily: "inherit", fontSize: 12.5,
    }}>
      <span style={{
        width: 30, height: 18, borderRadius: 10, position: "relative",
        background: checked ? "var(--accent)" : "var(--surface-2)",
        border: `1px solid ${checked ? "var(--accent)" : "var(--border)"}`,
      }}>
        <span style={{
          position: "absolute", top: 1, left: checked ? 13 : 1,
          width: 14, height: 14, background: "#fff", borderRadius: "50%",
          transition: "left 120ms var(--ease-standard)",
        }} />
      </span>
      <span>{label}</span>
    </button>
  );
}
function truncate(s, n) { return (s || "").length > n ? (s || "").slice(0, n - 1) + "…" : (s || ""); }
function slug(s)        { return (s || "untitled").toLowerCase().replace(/\s+/g, "-"); }

Object.assign(window, { TitleEditor, renderTitleCardDataUri });
