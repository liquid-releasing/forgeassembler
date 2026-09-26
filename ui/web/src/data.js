/* @esm-converted */
// The joiner catalogue — what a transition between two scenes can be.
//
// This file used to hold three synthetic sample projects (SMALL / MEDIUM /
// LARGE), placeholder SVG thumbnails, example user-authored joiner presets
// and a fake heatmap generator. All of it was design-time material for a
// hidden tweaks panel, and one of the projects was for a while the state
// the app booted into — so every launch opened on a compilation the user
// never made, pointing at files that did not exist.
//
// What is left is the one thing the app actually reads: the joiners.
//
// ── Two joiners, because the engine has two ────────────────────────
// `cli.py list-joiners` returns exactly `none` and `fade_to_black`. The
// catalogue here used to offer five: crossfade and swipe had no engine
// behind them at all (they were drawn disabled with a "soon" chip), and
// `dip_to_color` was the same engine joiner as fade-through-black with a
// different default colour — which the colour picker below already does.
//
// projectAdapter.joinerToReal still ACCEPTS `dip_to_color` on the way out,
// so a project file that carries one keeps forging correctly.

(function () {
  const JOINER_KINDS = [
    { kind: "none", label: "Cut",
      desc: "Straight cut. Previous frame ends, next frame begins.",
      icon: "minus",
      params: [],
      defaults: {},
    },
    { kind: "fade_through_black", label: "Fade through black",
      desc: "The scene fades out, black holds for a moment, the next scene fades in. One continuous transition with three parts.",
      icon: "circle-dot",
      params: [
        { id: "fadeOutS", label: "Fade out",   kind: "time", min: 0, max: 10, step: 0.1, default: 1.0, unit: "s" },
        { id: "holdS",    label: "Hold black", kind: "time", min: 0, max: 10, step: 0.1, default: 2.0, unit: "s" },
        { id: "fadeInS",  label: "Fade in",    kind: "time", min: 0, max: 10, step: 0.1, default: 1.0, unit: "s" },
        { id: "color",    label: "Hold color", kind: "color", default: "#000000" },
      ],
      // A second of fade, two seconds of black, a second back in: the
      // transition this app exists to make. The hold used to default to
      // 0.0s, which is a dissolve through black rather than a beat of
      // nothing between two scenes.
      defaults: { fadeOutS: 1.0, holdS: 2.0, fadeInS: 1.0, color: "#000000" },
    },
  ];

  const FADE_KINDS = ["fade_through_black", "dip_to_color"];

  function joinerKind(j) {
    return JOINER_KINDS.find(k => k.kind === j.kind) || JOINER_KINDS[0];
  }
  function joinerTotalMs(j) {
    if (j.kind === "none") return 0;
    if (FADE_KINDS.includes(j.kind)) {
      return Math.round(((j.fadeOutS || 0) + (j.holdS || 0) + (j.fadeInS || 0)) * 1000);
    }
    return Math.round((j.durationS || 0) * 1000);
  }
  function joinerShortLabel(j) {
    if (j.kind === "none") return "cut";
    const k = joinerKind(j);
    const totS = (joinerTotalMs(j) / 1000).toFixed(1);
    return `${k.label.toLowerCase()} · ${totS}s`;
  }

  const FA_DATA = {
    JOINER_KINDS,
    joinerKind, joinerTotalMs, joinerShortLabel,
  };
  window.FA_DATA = FA_DATA;
})();


export const FA_DATA = window.FA_DATA;
