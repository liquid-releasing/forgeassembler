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

## Later

- [ ] Section preview panel/popup — thumbnail strip + duration timeline of a section, possibly with overlays drawn on it. Render preview without a full ffmpeg pass.
- [ ] Text-card-as-section helper — atomically create a section with a black-background placeholder + text overlay (currently requires manually dropping a black PNG and adding a text overlay).
- [ ] text of the font and color actually being rendered in the text box

