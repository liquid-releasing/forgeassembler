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
        { id: "holdS",    label: "Hold black", kind: "time", min: 0, max: 10, step: 0.1, default: 3.0, unit: "s" },
        { id: "fadeInS",  label: "Fade in",    kind: "time", min: 0, max: 10, step: 0.1, default: 1.0, unit: "s" },
        { id: "color",    label: "Hold color", kind: "color", default: "#000000" },
      ],
      // A second of fade, three seconds of black, a second back in: five
      // seconds of joiner, which is the beat the user dialled in by hand on
      // the first real compilation. The hold used to default to 0.0s, which
      // is a dissolve through black rather than a beat of nothing between
      // two scenes, and then to 2.0s, which read as hurried.
      //
      // Read the arithmetic carefully: the fades do NOT add output time —
      // the engine applies them inside the scenes that already exist, so
      // only the hold lengthens the compilation. This default spans 5s of
      // transition and adds 3s per boundary. joinerTotalMs vs
      // joinerAddedMs below is exactly that distinction.
      defaults: { fadeOutS: 1.0, holdS: 3.0, fadeInS: 1.0, color: "#000000" },
    },
    { kind: "title_card", label: "Title", icon: "type",
      desc: "The scene fades out, a title card holds while its name is on screen, and the next scene fades in.",
      pickerHint: "New scenes fade into a title card naming the scene",
      params: [
        { id: "text",      label: "Title",       kind: "text", default: "" },
        { id: "fadeOutS",  label: "Fade out",    kind: "time", min: 0, max: 10, step: 0.1, default: 1.0, unit: "s" },
        { id: "holdS",     label: "Card on screen", kind: "time", min: 0.1, max: 20, step: 0.1, default: 3.0, unit: "s" },
        { id: "fadeInS",   label: "Fade in",     kind: "time", min: 0, max: 10, step: 0.1, default: 1.0, unit: "s" },
        { id: "background", label: "Card background", kind: "enum",
          options: ["color", "previous_last_frame", "next_first_frame"],
          labels: { color: "Colour",
                    previous_last_frame: "Last frame before",
                    next_first_frame: "First frame after" },
          default: "color" },
        { id: "backgroundDim", label: "Darken background", kind: "range",
          min: 0, max: 0.9, step: 0.05, default: 0.45 },
        { id: "fontSize",  label: "Font size",   kind: "range", min: 16, max: 240, step: 2, default: 96 },
        { id: "textColor", label: "Text colour", kind: "color", default: "#ffffff" },
        { id: "color",     label: "Card colour", kind: "color", default: "#000000" },
      ],
      // Same timing shape as the fade, because that is exactly what it
      // is: the card IS the hold. Only the hold adds output time.
      defaults: { text: "", fadeOutS: 1.0, holdS: 3.0, fadeInS: 1.0,
                  color: "#000000", textColor: "#ffffff", fontSize: 96,
                  background: "color", backgroundDim: 0.45 },
    },
  ];

  // Kinds built from fade-out / hold / fade-in. A title card is one of
  // them — the card IS the hold — so it gets the same arithmetic and
  // cannot drift from the fade's.
  const FADE_KINDS = ["fade_through_black", "dip_to_color", "title_card"];

  function joinerKind(j) {
    return JOINER_KINDS.find(k => k.kind === j.kind) || JOINER_KINDS[0];
  }
  // How long the transition READS as: fade out, hold, fade in. This is what
  // the joiner row and the editor footer show, because it is the span the
  // user is authoring.
  function joinerTotalMs(j) {
    if (j.kind === "none") return 0;
    if (FADE_KINDS.includes(j.kind)) {
      return Math.round(((j.fadeOutS || 0) + (j.holdS || 0) + (j.fadeInS || 0)) * 1000);
    }
    return Math.round((j.durationS || 0) * 1000);
  }

  // How much time the joiner ADDS to the output — which is only the hold.
  //
  // The engine is explicit about this in its own params_schema: `fade_s` is
  // "applied within the existing segments — does not add to the output
  // duration", while `duration_s` is the solid-colour bridge between them.
  // Measured on a real forge: two 40s scenes with a 1s/2s/1s fade produced
  // 82.03s, and the chapters landed at 0-42000 and 42000-82000. Scene plus
  // HOLD, not scene plus the whole transition.
  //
  // Using joinerTotalMs for duration arithmetic over-reported every total
  // and every chapter time by fade-out + fade-in per boundary — 2s each
  // with the default fade.
  function joinerAddedMs(j) {
    if (j.kind === "none") return 0;
    if (FADE_KINDS.includes(j.kind)) return Math.round((j.holdS || 0) * 1000);
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
    joinerKind, joinerTotalMs, joinerAddedMs, joinerShortLabel,
  };
  window.FA_DATA = FA_DATA;
})();


export const FA_DATA = window.FA_DATA;
