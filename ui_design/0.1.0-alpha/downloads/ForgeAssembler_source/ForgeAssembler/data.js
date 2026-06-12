// Synthetic ForgeAssembler project data — three sample sizes.
// Model mirrors the real .forgeproject.json:
//   Project → Sections (each w/ leading joiner) → Segments
//   plus a separate `audioBeds` lane that spans multiple segments.

(function () {
  // ── Thumbnail placeholders — labeled coloured rects via inline SVG ─
  // Each clip thumb is a tiny SVG data URI so we don't depend on assets.
  // Hot / dark / blue / steel palettes pulled from the brand vibe (anvil + sparks).
  function thumb(label, hue = 18, dark = false) {
    const a = dark ? 12 : 28;
    const b = dark ? 4  : 14;
    const svg = `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 160 90'>
      <defs>
        <linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>
          <stop offset='0' stop-color='oklch(${a}% 0.08 ${hue})'/>
          <stop offset='1' stop-color='oklch(${b}% 0.05 ${hue})'/>
        </linearGradient>
      </defs>
      <rect width='160' height='90' fill='url(#g)'/>
      <g fill='oklch(58% 0.16 ${hue} / 0.55)'>
        <circle cx='40' cy='38' r='2'/><circle cx='62' cy='27' r='1.4'/>
        <circle cx='118' cy='51' r='1.8'/><circle cx='98' cy='62' r='1.2'/>
        <circle cx='27' cy='66' r='1.5'/><circle cx='142' cy='24' r='1.6'/>
      </g>
      <text x='80' y='52' text-anchor='middle' font-family='JetBrains Mono, monospace'
            font-size='9' font-weight='600' fill='oklch(80% 0.06 ${hue})' letter-spacing='0.06em'>
        ${label.toUpperCase()}
      </text>
    </svg>`;
    return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
  }

  // ── Channel keys (mirrors core.OutputChannels) ─────────────────────
  const CHANNELS = [
    { id: "main",        label: "2D main",         desc: ".funscript"             },
    { id: "multi_axis",  label: "Multi-axis",      desc: "pitch / roll / surge"   },
    { id: "estim_3p",    label: "3-phase estim",   desc: "alpha + beta"           },
    { id: "estim_4p",    label: "4-phase estim",   desc: "phase 2",      future: true },
    { id: "alt",         label: "Alternate funscripts", desc: ".alt.funscript variants" },
    { id: "audio_estim", label: "Haptic-estim audio", desc: ".stereostim.wav"     },
    { id: "pulse_freq",  label: "Pulse frequency", desc: "phase 2",     future: true },
  ];

  // ── Small project — 4 segments, 2 sections, one audio bed ────────────
  const SMALL = {
    name: "lqr_marketing",
    output: { resolution: "1080p", normalizeAudio: true, video: true, funscripts: false },
    channels: { main: true, multi_axis: false, estim_3p: false, alt: false, audio_estim: false },
    sections: [
      {
        id: "sec-1", title: "Opening title", color: "#ff8c42",
        joiner: { type: "none" },
        segments: [
          { id: "s1", title: "Steel pour", file: "149727107-tank-pours-liquid-metal-steel.mp4",
            kind: "video", durMs: 6200, thumb: thumb("steel pour", 28),
            channels: ["main"], overlays: 1, audio: "keep", temp: 0 },
          { id: "s2", title: "FunscriptForge banner", file: "funscriptforge-banner.png",
            kind: "still", durMs: 5000, thumb: thumb("banner png", 18, true),
            channels: [], overlays: 0, audio: "silence", temp: 0 },
        ],
      },
      {
        id: "sec-2", title: "Mechanical demo", color: "#ff4b4b",
        joiner: { kind: "fade_through_black", fadeOutS: 2.5, holdS: 0.5, fadeInS: 2.5, color: "#1a1a1a" },
        segments: [
          { id: "s3", title: "Mechanical motion", file: "funscriptforge-mechanical.mp4",
            kind: "video", durMs: 24500, thumb: thumb("mechanical", 240),
            channels: ["main", "multi_axis"], overlays: 0, audio: "replace",
            audioFile: "funscriptmechanicalaudio.mp3", temp: 0 },
          { id: "s4", title: "Closing slate", file: "1085-142801793.mp4",
            kind: "video", durMs: 8000, thumb: thumb("closing", 28),
            channels: ["main"], overlays: 1, audio: "keep", temp: 200 },
        ],
      },
    ],
    audioBeds: [
      { id: "bed-1", file: "underground-house.mp3", title: "Hypnotic Underground Tech House",
        startSegmentId: "s2", endSegmentId: "s4", level: -16, fadeInS: 2, fadeOutS: 3, duckUnderSegmentAudio: true },
    ],
  };

  // ── Medium — 8 segments, 3 sections, 2 audio beds ────────────────────
  const MEDIUM = {
    name: "vol_03_compilation",
    output: { resolution: "1080p", normalizeAudio: true, video: true, funscripts: true },
    channels: { main: true, multi_axis: true, estim_3p: true, alt: false, audio_estim: true },
    sections: [
      {
        id: "m-sec-1", title: "Cold open", color: "#ff8c42",
        joiner: { type: "none" },
        segments: [
          { id: "m1", title: "Liquid releasing — open", file: "lqr_open.mp4",
            kind: "video", durMs: 4000, thumb: thumb("open", 28),
            channels: ["main", "estim_3p"], overlays: 0, audio: "keep", temp: 0 },
          { id: "m2", title: "Chapter 1 plate", file: "ch1_plate.png",
            kind: "still", durMs: 3500, thumb: thumb("ch.1", 18, true),
            channels: [], overlays: 0, audio: "silence", temp: 0 },
        ],
      },
      {
        id: "m-sec-2", title: "Chapter 1 · Build", color: "#ff4b4b",
        joiner: { kind: "fade_through_black", fadeOutS: 1.25, holdS: 0, fadeInS: 1.25, color: "#000000" },
        segments: [
          { id: "m3", title: "ipzz125 · cut 01", file: "ipzz125_01.mp4",
            kind: "video", durMs: 184000, thumb: thumb("ipzz125 01", 12),
            channels: ["main", "multi_axis", "estim_3p"], overlays: 0, audio: "keep", temp: -100 },
          { id: "m4", title: "ipzz125 · cut 02", file: "ipzz125_02.mp4",
            kind: "video", durMs: 142000, thumb: thumb("ipzz125 02", 12),
            channels: ["main", "multi_axis", "estim_3p"], overlays: 0, audio: "keep", temp: -100 },
          { id: "m5", title: "Victoria Oats · cut", file: "vict_oats_cut.mp4",
            kind: "video", durMs: 96500, thumb: thumb("v.oats", 28),
            channels: ["main", "estim_3p"], overlays: 0, audio: "keep", temp: 0 },
        ],
      },
      {
        id: "m-sec-3", title: "Chapter 2 · Crest", color: "#ff5470",
        joiner: { kind: "swipe", durationS: 0.6, direction: "ltr", easing: "ease-in-out", softness: 8 },
        segments: [
          { id: "m6", title: "Chapter 2 plate", file: "ch2_plate.png",
            kind: "still", durMs: 4000, thumb: thumb("ch.2", 18, true),
            channels: [], overlays: 0, audio: "silence", temp: 0 },
          { id: "m7", title: "Big buck bunny montage", file: "bbb_montage.mp4",
            kind: "video", durMs: 78000, thumb: thumb("montage", 60),
            channels: ["main", "multi_axis"], overlays: 1, audio: "replace",
            audioFile: "ambient_pad.wav", temp: 0 },
          { id: "m8", title: "Liquid releasing · exit", file: "lqr_exit.mp4",
            kind: "video", durMs: 8500, thumb: thumb("exit", 28),
            channels: ["main"], overlays: 0, audio: "keep", temp: 0 },
        ],
      },
    ],
    audioBeds: [
      { id: "bed-m1", file: "underground-house.mp3", title: "Hypnotic Tech House",
        startSegmentId: "m2", endSegmentId: "m5", level: -18, fadeInS: 2, fadeOutS: 4, duckUnderSegmentAudio: true },
      { id: "bed-m2", file: "soothing-waterfall.mp3", title: "Soothing waterfall (ASMR)",
        startSegmentId: "m6", endSegmentId: "m8", level: -22, fadeInS: 3, fadeOutS: 3, duckUnderSegmentAudio: false },
    ],
  };

  // ── Large — 14 segments across 4 sections, 3 audio beds ──────────────
  const LARGE = {
    name: "longform_session_aug",
    output: { resolution: "1440p", normalizeAudio: true, video: true, funscripts: true },
    channels: { main: true, multi_axis: true, estim_3p: true, alt: true, audio_estim: true },
    sections: [
      {
        id: "l-sec-1", title: "Opening", color: "#ff8c42",
        joiner: { type: "none" },
        segments: [
          { id: "l1", title: "Steel pour intro", file: "steel_pour.mp4",
            kind: "video", durMs: 6200, thumb: thumb("steel", 28),
            channels: ["main"], overlays: 1, audio: "keep", temp: 0 },
          { id: "l2", title: "Title plate", file: "title_plate.png",
            kind: "still", durMs: 4500, thumb: thumb("title", 18, true),
            channels: [], overlays: 0, audio: "silence", temp: 0 },
        ],
      },
      {
        id: "l-sec-2", title: "Act I · Tender → Build", color: "#ff4b4b",
        joiner: { kind: "fade_through_black", fadeOutS: 1.25, holdS: 0, fadeInS: 1.25, color: "#1a1a1a" },
        segments: [
          { id: "l3", title: "Cut 01 · tender", durMs: 124000, kind: "video", file: "act1_01.mp4",
            thumb: thumb("tender 01", 240), channels: ["main", "estim_3p"], overlays: 0, audio: "keep", temp: -50 },
          { id: "l4", title: "Cut 02 · tender",   durMs:  92000, kind: "video", file: "act1_02.mp4",
            thumb: thumb("tender 02", 240), channels: ["main", "estim_3p"], overlays: 0, audio: "keep", temp: -50 },
          { id: "l5", title: "Cut 03 · build",    durMs: 156000, kind: "video", file: "act1_03.mp4",
            thumb: thumb("build 03", 12),   channels: ["main", "multi_axis", "estim_3p"], overlays: 0, audio: "keep", temp: 0 },
          { id: "l6", title: "Cut 04 · build",    durMs: 138000, kind: "video", file: "act1_04.mp4",
            thumb: thumb("build 04", 12),   channels: ["main", "multi_axis", "estim_3p"], overlays: 0, audio: "keep", temp: 0 },
        ],
      },
      {
        id: "l-sec-3", title: "Act II · Tease → Edge", color: "#ff5470",
        joiner: { kind: "crossfade", durationS: 1.2, easing: "ease-in-out" },
        segments: [
          { id: "l7",  title: "Chapter plate", durMs: 4000, kind: "still", file: "act2_plate.png",
            thumb: thumb("act ii", 18, true), channels: [], overlays: 0, audio: "silence", temp: 0 },
          { id: "l8",  title: "Cut 05 · tease", durMs: 102000, kind: "video", file: "act2_01.mp4",
            thumb: thumb("tease 05", 60),     channels: ["main", "multi_axis", "estim_3p", "alt"], overlays: 0, audio: "keep", temp: 0 },
          { id: "l9",  title: "Cut 06 · edge",   durMs:  88000, kind: "video", file: "act2_02.mp4",
            thumb: thumb("edge 06", 28),      channels: ["main", "multi_axis", "estim_3p", "alt"], overlays: 0, audio: "keep", temp: 0 },
          { id: "l10", title: "Cut 07 · edge",   durMs:  74000, kind: "video", file: "act2_03.mp4",
            thumb: thumb("edge 07", 28),      channels: ["main", "multi_axis", "estim_3p", "alt"], overlays: 0, audio: "keep", temp: 0 },
        ],
      },
      {
        id: "l-sec-4", title: "Act III · Climax → Outro", color: "#c93535",
        joiner: { kind: "fade_through_black", fadeOutS: 2.0, holdS: 0.5, fadeInS: 2.0, color: "#1a0e1e" },
        segments: [
          { id: "l11", title: "Cut 08 · climax", durMs: 168000, kind: "video", file: "act3_01.mp4",
            thumb: thumb("climax 08", 12),    channels: ["main", "multi_axis", "estim_3p", "alt"], overlays: 0, audio: "keep", temp: 0 },
          { id: "l12", title: "Cut 09 · cooldown", durMs: 84000, kind: "video", file: "act3_02.mp4",
            thumb: thumb("cool 09", 240),     channels: ["main", "estim_3p"], overlays: 0, audio: "keep", temp: 0 },
          { id: "l13", title: "Closing slate", durMs: 5000, kind: "still", file: "closing.png",
            thumb: thumb("closing", 18, true), channels: [], overlays: 1, audio: "silence", temp: 0 },
          { id: "l14", title: "Liquid releasing · exit", durMs: 9500, kind: "video", file: "lqr_exit.mp4",
            thumb: thumb("lqr exit", 28),    channels: ["main"], overlays: 0, audio: "keep", temp: 0 },
        ],
      },
    ],
    audioBeds: [
      { id: "bed-l1", file: "ambient_warm.mp3", title: "Warm ambient bed",
        startSegmentId: "l3", endSegmentId: "l6", level: -18, fadeInS: 2, fadeOutS: 3, duckUnderSegmentAudio: true },
      { id: "bed-l2", file: "tech_house.mp3", title: "Tech house · 124 bpm",
        startSegmentId: "l8", endSegmentId: "l10", level: -16, fadeInS: 2, fadeOutS: 3, duckUnderSegmentAudio: true },
      { id: "bed-l3", file: "soothing_outro.mp3", title: "Soothing outro pad",
        startSegmentId: "l11", endSegmentId: "l14", level: -20, fadeInS: 4, fadeOutS: 5, duckUnderSegmentAudio: false },
    ],
  };

  // ── Joiner kinds catalog — built-in joiner templates ────────────────
  // Each "kind" defines its parameter shape and defaults. User joiners
  // are presets on top of these kinds with their own param defaults.
  const JOINER_KINDS = [
    { kind: "none", label: "Cut",
      desc: "Straight cut. Previous frame ends, next frame begins. The default.",
      icon: "minus",
      params: [],
      defaults: {},
    },
    { kind: "fade_through_black", label: "Fade through black",
      desc: "Previous clip fades out, holds black for an optional interval, next clip fades in. One continuous transition with three parts.",
      icon: "circle-dot",
      params: [
        { id: "fadeOutS", label: "Fade out",   kind: "time", min: 0, max: 10, step: 0.1, default: 1.5, unit: "s" },
        { id: "holdS",    label: "Hold black", kind: "time", min: 0, max: 10, step: 0.1, default: 0.0, unit: "s" },
        { id: "fadeInS",  label: "Fade in",    kind: "time", min: 0, max: 10, step: 0.1, default: 1.5, unit: "s" },
        { id: "color",    label: "Hold color", kind: "color", default: "#000000" },
      ],
      defaults: { fadeOutS: 1.5, holdS: 0.0, fadeInS: 1.5, color: "#000000" },
    },
    { kind: "crossfade", label: "Crossfade",
      desc: "Dissolve from the previous clip into the next. Overlapping in time.",
      icon: "git-pull-request-arrow",
      params: [
        { id: "durationS", label: "Duration", kind: "time",  min: 0.1, max: 10, step: 0.1, default: 1.0, unit: "s" },
        { id: "easing",    label: "Easing",    kind: "enum",  default: "ease-in-out",
          options: ["linear", "ease-in", "ease-out", "ease-in-out"] },
      ],
      defaults: { durationS: 1.0, easing: "ease-in-out" },
    },
    { kind: "dip_to_color", label: "Dip to color",
      desc: "Like fade through black, but the hold color is yours to pick — useful for white, brand colour, or a mood wash.",
      icon: "droplet",
      params: [
        { id: "fadeOutS", label: "Fade out",   kind: "time",  min: 0, max: 10, step: 0.1, default: 1.0, unit: "s" },
        { id: "holdS",    label: "Hold",        kind: "time",  min: 0, max: 10, step: 0.1, default: 0.2, unit: "s" },
        { id: "fadeInS",  label: "Fade in",    kind: "time",  min: 0, max: 10, step: 0.1, default: 1.0, unit: "s" },
        { id: "color",    label: "Hold color",  kind: "color", default: "#fafafa" },
      ],
      defaults: { fadeOutS: 1.0, holdS: 0.2, fadeInS: 1.0, color: "#fafafa" },
    },
    { kind: "swipe", label: "Swipe",
      desc: "Push the next clip in from one edge. Soft-edged wipe between clips.",
      icon: "move-horizontal",
      params: [
        { id: "durationS", label: "Duration",  kind: "time", min: 0.1, max: 5,  step: 0.1, default: 0.6, unit: "s" },
        { id: "direction", label: "Direction", kind: "enum", default: "ltr",
          options: ["ltr", "rtl", "ttb", "btt"] },
        { id: "easing",    label: "Easing",    kind: "enum", default: "ease-in-out",
          options: ["linear", "ease-in", "ease-out", "ease-in-out"] },
        { id: "softness",  label: "Edge softness", kind: "range", min: 0, max: 100, step: 1, default: 8, unit: "%" },
      ],
      defaults: { durationS: 0.6, direction: "ltr", easing: "ease-in-out", softness: 8 },
    },
  ];

  // A few example user-authored joiner presets seeded per project.
  const SAMPLE_USER_JOINERS = [
    { id: "uj-quick-fade", name: "Quick fade", builtOn: "fade_through_black",
      params: { fadeOutS: 0.4, holdS: 0, fadeInS: 0.4, color: "#000000" } },
    { id: "uj-long-breath", name: "Long breath", builtOn: "fade_through_black",
      params: { fadeOutS: 3.5, holdS: 1.5, fadeInS: 3.5, color: "#1a0e1e" } },
    { id: "uj-brand-dip", name: "Brand dip · red", builtOn: "dip_to_color",
      params: { fadeOutS: 0.8, holdS: 0.15, fadeInS: 0.8, color: "#ff4b4b" } },
  ];

  for (const p of [SMALL, MEDIUM, LARGE]) {
    p.userJoiners = JSON.parse(JSON.stringify(SAMPLE_USER_JOINERS));
  }

  function joinerKind(j) {
    return JOINER_KINDS.find(k => k.kind === j.kind) || JOINER_KINDS[0];
  }
  function joinerTotalMs(j) {
    if (j.kind === "none") return 0;
    if (j.kind === "fade_through_black" || j.kind === "dip_to_color") {
      return Math.round(((j.fadeOutS || 0) + (j.holdS || 0) + (j.fadeInS || 0)) * 1000);
    }
    return Math.round((j.durationS || 0) * 1000);
  }
  function joinerShortLabel(j, userJoiners = []) {
    if (j.kind === "none") return "cut";
    const matchPreset = userJoiners.find(u => u.builtOn === j.kind &&
      Object.entries(u.params).every(([k, v]) => j[k] === v));
    if (matchPreset) return matchPreset.name.toLowerCase();
    const k = joinerKind(j);
    const totS = (joinerTotalMs(j) / 1000).toFixed(1);
    return `${k.label.toLowerCase()} · ${totS}s`;
  }

  // ── Synthesize fake heatmap + beatmap velocity bins ─────────────────
  function makeHeatmap(project) {
    // One bin per ~1s of total duration, value 0-1, mock the perceptual gradient
    const totalMs = project.sections.flatMap(s => s.segments).reduce((a, s) => a + s.durMs, 0);
    const bins = Math.max(60, Math.min(900, Math.round(totalMs / 1000)));
    const arr = [];
    let i = 0;
    for (const sec of project.sections) {
      for (const seg of sec.segments) {
        const n = Math.max(2, Math.round((seg.durMs / totalMs) * bins));
        const isStill = seg.kind === "still";
        for (let k = 0; k < n; k++) {
          const t = k / n;
          // Build a phrase-y curve per clip
          let v;
          if (isStill) v = 0.03;
          else {
            // Sin-wave pulse modulated by a slow envelope unique per clip
            const seed = (parseInt((seg.id.match(/\d+/) || ["3"])[0], 10) * 13) % 100 / 100;
            v = 0.18 + 0.55 * Math.abs(Math.sin(t * Math.PI * 6 + seed * 7))
                + 0.25 * Math.sin(t * Math.PI * 1.7 + seed * 3);
            v = Math.max(0.02, Math.min(0.98, v));
          }
          arr.push({ v, segId: seg.id, sectionId: sec.id, color: sec.color });
          i++;
        }
      }
    }
    return arr;
  }

  // ── Public exports ──────────────────────────────────────────────────
  const FA_DATA = {
    CHANNELS,
    PROJECTS: { small: SMALL, medium: MEDIUM, large: LARGE },
    JOINER_KINDS,
    joinerKind, joinerTotalMs, joinerShortLabel,
    makeHeatmap,
  };
  window.FA_DATA = FA_DATA;
})();
