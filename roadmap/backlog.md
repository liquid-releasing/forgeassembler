# backlog of features

## v0.0.2 (shipped 2026-04-25)

- [x] Ability to edit a section, not just the last one — focus + collapse + Done editing
- [x] Insert a new section above or below a focused one
- [x] Replace a clip's video file in place (preserves overlays + auto-rescans funscripts)
- [x] Split a section between two clips, with smart overlay redistribution
- [x] Clean up the buttons in section editing — 🔪 Split moved between clips, 📝/🗑/🔄 colored, dur/replace/delete laid out per row

## v0.0.3 (next)

- [x] **Trim & Split-at-time** — supersedes the "multi-chapter per section" entry. Splitting a single clip at a source-file timestamp turns into four features: trim-start, trim-end, multi-chapter, and mid-video fade-to-black. The second piece auto-promotes to a new section (= a new chapter). Bottom-up math goes away because the split timestamp always refers to the original file.
- [ ] **Concat alternative haptic audio** — concat per-channel audio (`.stereostim.wav`, `.legacy.wav`, `.prostate.stereostim.wav`) in lock-step with video segments. Detection already wired in `detect.py`; engine path explicitly defers it (`concat_funscript.py:186` "audio_estim deferred to Phase 2"). Need test media + lock-step concat path with silence-fill for clips missing the channel.
- [ ] **DemoForge microeditor** — script-driven AI narration per section (ElevenLabs first; pluggable). Auto-place generated audio as a section audio overlay; auto-pad video where narration is longer. See agent memory for the full vision (audience-of-one presentation engine, Carta tie-in, slides + video + narration trio).

## v0.0.4 (queued)

- [ ] **Smoothing at section boundaries** — option to ease funscript actions across hard cuts so devices don't snap from one position to another at the boundary. Concat is currently raw "hold last position" (concat_funscript.py docstring). Design questions: configurable cushion window (e.g. 250ms), per-channel toggle vs project-wide, easing curve (linear / cosine), interaction with fade_to_black joiners (already softens via silent bridge — cushion may be redundant or additive). User can simulate today by using fade_to_black between sections.

## v0.0.5 (queued)

- [ ] **Help menu in the title bar** — Documentation (link to the mkdocs site), Discord (community link), and About. Now a Tauri menu: build it in Rust (`tauri::menu`) and open links through the `opener` path the app already uses for reveal/open-external. macOS gets a full menu bar; on Windows + Linux decide between a native menu and an in-app Help control.

- [ ] **Auto-synthesize haptic audio from funscripts** — when a segment has a funscript but no sibling `.stereostim.wav` / `.legacy.wav` / `.prostate.stereostim.wav`, generate the audio inline at forge time. **This is a capability win, not just a convenience:** restim's UI is genuinely hard to coax into emitting prostate audio from an existing funscript, so even users WITH restim installed can't easily produce all three channels manually. FA's synth path takes the funscript straight through vendored `stim_math` and emits the audio directly. Vendor `stim_math` narrowly (same pattern as ForgePlayer's restim integration — pinned commit, attribution). Cache generated audio so a re-forge of unchanged segments doesn't re-synthesize. Cache location TBD (alongside source funscripts? per-project `.cache/audio_estim/`?). Builds on v0.0.4 concat machinery — that pipeline already silence-fills missing segments; this replaces silence with on-demand synthesis where a funscript exists.
- [ ] **Per-channel missing-audio policy** — paired with the auto-synthesize feature. Today (v0.0.4) the only behavior for a missing segment file is silence-fill. Once we can synthesize, expose a per-channel choice: **synthesize** (default if funscript exists), **silence-fill** (current behavior, e.g. for intentional gaps), **skip-emit** (drop the channel entirely if any segment is missing — strict-lockstep mode). User has "a great idea" for this — capture when revisiting.
- [ ] **Audio across multiple sections** — let an audio overlay (music bed, narration, voiceover) span more than one section without copy-pasting it onto each. Today every audio overlay is anchored to a single Section, so a music bed playing across sections 2-5 has to be added four times with manual time math. Want a project-level "audio bed" with a section-range (or absolute time-range) and the same fade in/out / mix_pct controls. Connects to the "beat track that I can fade in and out" ask from yesterday's planning, and to the DemoForge narration story (a single narration that flows across slide + screencast sections without per-section duplication). Note: the Project model already declares `audio_beds: list[dict]` but the engine doesn't render it yet — wire it through.

## Later

- [ ] Section preview panel/popup — thumbnail strip + duration timeline of a section, possibly with overlays drawn on it. Render preview without a full ffmpeg pass.
- [ ] Text-card-as-section helper — atomically create a section with a black-background placeholder + text overlay (currently requires manually dropping a black PNG and adding a text overlay).
- [ ] text of the font and color actually being rendered in the text box

## Next — after v0.1.0-alpha

- [ ] **Mark a compilation complete.** The Viewer (stage 04) ends the chain,
  and a chain that ends with nothing to press just trails off. FunscriptForge's
  Viewer has a red accept/checkmark whose whole value is marking the moment.
  Record it in the `.forge` as `completion: {state, at, by}` and show it on the
  Home screen's recents, so a finished compilation looks finished next session.
  It must gate nothing. Spec:
  `funscriptforge/internal/DESIGN_forge_bundle_renditions_and_completion.md`.
- [ ] **Renditions in the `.forge`.** One compilation, several video files
  (`Best Of.4k25.mp4`, `Best Of.1080p25.mp4`). The filename tag already lets
  them coexist on disk; the bundle should list them so ForgePlayer can offer a
  quality picker. A sibling of `media`, never a retype of it, and a list of
  candidates rather than promises — ship the 1080p to someone and their bundle
  names a 4K they do not have. Same spec file.
- [ ] **`--resolution` / `--frame-rate` overrides on `cli.py forge`.** Makes a
  scripted second render possible without hand-editing the project JSON, which
  is what the docs page currently has to leave out. No render QUEUE: that was
  considered and cut — it saves ~30s of clicking on a 20-minute job.
- [ ] **Name the gap fix for what it does.** A scene missing a channel needs
  one of two different things, and the app can already tell which: if the
  channel is in the project's `polish/` folder but not the bundle, the bundle
  is stale and FSF `refresh` fixes it; if it is absent from the project too
  (`surge`/`sway` depend on the multi-axis style the author chose) only FSF
  can, and that is an authoring decision. Offer "Re-export scene" or "Open in
  FunscriptForge" accordingly — never a hopeful "Fixme".
- [ ] **Show which bundle version a scene is on** — filename, date, channel
  count, and a note when a newer sibling sits beside it.

## Branding — decided 2026-09-28, partly built

An optional `.forge` scene at each end of a compilation. It is a scene like
any other, so it brings its own audio AND funscripts — which is the point of
the intro: it plays before any content, so it doubles as a calibration run.

**Built:** the engine half. `Output.branding_intro` / `branding_outro` are
resolved Segments threaded through `Project.items`, so the layout, the
filtergraph, the chapter offsets and the title-card background frame all
follow. Plus the Output tab's Branding card. 11 tests in `test_branding.py`.

Decisions, so none of these get re-litigated:

- **Both ends**, each independently optional.
- **Branding, then the title page.** Cinema order, it puts the calibration
  funscripts at absolute zero, and it gives the compilation's title card a
  clip to sit over — `previous_last_frame` walks BACK through `items` for the
  nearest segment, and before branding there was nothing behind the first
  card to find. The user asked for exactly that: "the title page should be
  able to grab the last image from branding for its background."
- **No chapter marker.** Chapter 01 stays the first real scene, so a viewer
  skipping to it lands on content. Branding still pushes chapter 01 later by
  its own length, which falls out of the layout for free.
- **Stored in the project, not in a studio profile.** Considered and
  rejected (2026-09-28): a profile would let one logo change reach every
  project, at the cost of the project file no longer determining its own
  output. The user chose the project. ⚠ The consequence is that changing your
  branding means re-picking it per project.
- **`segments()` stays content-only; `timeline_segments()` includes
  branding.** The loudest caller of `segments()` asks "what resolution is the
  source?", and that must follow the footage rather than a bumper authored at
  some other size.

### Still to build

- [ ] **A branding FOLDER setting.** Adding a folder of scenes will never
  contain the branding, so the app needs a known place to look. One
  remembered folder (`D:\brand\` — `intro.forge`, `outro.forge`, `logo.png`)
  that the Branding pickers open into, instead of wherever Windows last was.
  Per-machine, like the existing folder memory. The per-project storage is
  unchanged; the folder only replaces the picker's starting point.
- [ ] **Logo on the branding.** ENGINE ALREADY DOES THIS — segments carry
  image overlays ("logo, lower-third, etc."), each becoming a looped PNG
  input with position, timing and fades. UI only: attach an image overlay at
  `br` to the branding segment. Scoped to the branding by construction,
  because it lives on that segment.
- [ ] **Segment-level TEXT overlays.** The one real engine gap:
  `concat_video` has `if ov.type != "image": continue  # text overlays
  deferred to a later phase`. Section-level text is fully implemented and
  proven (`text_overlay_filter`, the 9-position grid, `text_align`,
  `_build_text_files`), and it applies drawtext to the CONCATENATED video at
  absolute times — so the segment version computes the segment's absolute
  window from the layout and does the same. ⚠ Segment `Overlay` has no `id`
  (section overlays do) and `_build_text_files` keys on it — key segment ones
  by (segment id, index). ⚠ The two models name fields differently:
  `content`/`size`/`color`/`end_s` vs `text`/`font_size`/`text_color`/
  `duration_s`. Map between them; do not retype either, both are persisted.
- [ ] **Credits.** NOT a card — a static multi-line white text overlay on the
  OUTRO bumper's own footage, lower part of frame, no scrolling. Defaults:
  starts 5s into the outro, holds 10s, fades out. The user's outro is 20s,
  which leaves a 5s tail. Everything the model needs already exists:
  `color` already defaults to `#ffffff`, `position: "bc"` is in the grid, and
  drawtext renders newlines from a `textfile=`.
