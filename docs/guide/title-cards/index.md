# Title Cards

A title card in ForgeAssembler is simply a **segment whose video is a
PNG**. The PNG is held on screen for a configurable duration and
concatenates into the final output alongside regular video clips.

ForgeAssembler deliberately does **no typography or text layout** —
that belongs in your design tool of choice. These guides show you how
to build title cards in [Figma](https://www.figma.com/) (free) at the
exact pixel dimensions ForgeAssembler supports.

---

## Which guide should I start with?

| Guide | When to use it | Difficulty |
|---|---|---|
| [White on Transparent](getting_started_white_on_transparent.md) | Clean section headers, lower-third captions, plain titles | Beginner |
| [Black Cutout](getting_started_black_cutout.md) | Dramatic "scope reveal" effect where letters are transparent holes | Beginner+ |
| [Sci-Fi Cockpit Example](scifi_cockpit_example.md) | Themed HUD look with neon outlines, glow, and accent bars | Intermediate |

All three guides are fully self-contained and assume no prior Figma
experience. Each walks you through exactly one technique, end to end,
and ends with a section on dropping the PNG into ForgeAssembler as a
segment.

---

## Supported resolutions

Every guide produces PNGs at any of ForgeAssembler's canonical output
sizes. Match your title card resolution to the project's output
resolution for best results (no scaling in the forged video).

| Name in ForgeAssembler | Width × Height | Aspect |
|---|---|---|
| `1080p` (default) | 1920 × 1080 | 16:9 |
| `1440p` | 2560 × 1440 | 16:9 |
| `4k` | 3840 × 2160 | 16:9 |
| `uw_1080p` | 2560 × 1080 | 21:9 UltraWide |
| `uw_1440p` | 3440 × 1440 | 21:9 UltraWide |
| `4_3_hd` | 1440 × 1080 | 4:3 |
| `3_4_hd` | 1080 × 1440 | 3:4 portrait |
| `9_16_hd` | 1080 × 1920 | 9:16 portrait (TikTok/Reels) |
