Project I/O is wired up.

TopBar — status indicator next to the filename:

unsaved (warm pill) when project has no path yet
unsaved changes (amber) when there's a path but edits since last save
saved (green) when fully synced; subtitle adds "saved just now / 2 min ago / 1h ago"
The Save button label adapts: "Save as…" (no path) → "Save changes" (dirty, primary-styled) → "Saved" (clean, secondary)
Save As dialog (first save, or new project):

File name field (slugged into <basename>.forgeproject.json)
Folder field + Browse button
Live preview of the path being written
Brief "what gets written now" callout that distinguishes the JSON sidecar from the forged outputs
Open Project dialog:

"Browse for a file…" card at the top with primary button (would open OS dialog)
"Recent projects" list — 4 mock recents with path, when, clip count, duration; click any to open
Esc / outside-click closes
Unsaved changes prompt — automatically intercepts the Open flow when there are unsaved changes:

Modal: "Save changes? name.forgeproject.json has unsaved changes."
Three actions: Cancel · Don't save · Save and continue
Save and continue routes through the Save dialog if there's no path yet; otherwise saves in place, then opens the Open dialog automatically
Dirty flag is set by every mutation handler (joiner edits, renames, drag-reorder, title additions/overlays, bulk ops, user joiner CRUD). Switching the sample-size tweak resets to "fresh unsaved" so you can demo Save As again.

Three new placement + glyph + template capabilities now in the title editor:

Position grid (9 cells) — In overlay mode, replaces the read-only "position is set by the layout" text with a 3×3 picker. Each layout has a default cell (marked with a warm-orange dot); the user can override to any of the 9 corners/edges/center. The preview repositions the type in real time. Available positions: top-left · top-center · top-right · middle-left · center · middle-right · bottom-left · bottom-center · bottom-right.

Glyph picker — The old "show anvil glyph" toggle is now a row of 7 built-in glyphs (none · anvil · hammer · tongs · oven · spark · dot) plus a dashed + custom tile that opens a file picker (SVG or PNG). Uploaded glyphs are stored as data URIs in the project's userGlyphs list, marked with a small "custom" tag, and selectable forever after.

Templates row — A new section at the top of the modal showing the four built-in layouts as thumbnails plus any user-saved templates (with a "saved" badge). Click any card to load its layout/theme/glyph/position into the current draft. A new Save as template… button in the footer prompts for a name and persists the current styling to the project's userTitleTemplates list.

All three persist on the project — the dirty flag picks them up, and saving via the existing Save / Save As flow includes them in the .forgeproject.json sidecar alongside user joiners.