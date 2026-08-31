# ForgeAssembler

Build a long haptic video from many short ones. Edit the individual clips in [FunscriptForge](https://github.com/liquid-releasing/funscriptforge), then assemble them into a combined video + combined funscripts with configurable transitions between segments.

A small, local desktop app — no account, no cloud, no telemetry. Runs on Windows, macOS, and Linux.

**Download:** [latest release](https://github.com/liquid-releasing/forgeassembler-releases/releases/latest) · **Community:** [Discord](https://discord.gg/UHdJFhEZF)

---

## What it does

1. **Add segments**: point at a folder (or single file). ForgeAssembler detects the video and all associated funscripts (main, multi-axis, estim channels, etc.).
2. **Pick joiners**: choose what goes between two segments — no joiner (straight cut), fade-to-black, or a title card.
3. **Select output channels**: which funscript variants should the combined output include (2D main, multi-axis, 3-phase estim, prostate, audio, pulse-frequency).
4. **Forge**: ForgeAssembler concatenates the videos with ffmpeg, concatenates every selected funscript channel in lockstep with timestamp-corrected actions, writes chapter markers at every segment boundary, and saves the project as reusable JSON.

## Project files

Every forge writes a `.forgeproject.json` alongside the output. It describes the ordered item list, the joiners, the output channel selection, and the paths. You can hand-edit this file to reorder segments or tweak joiner settings, then reload it into ForgeAssembler.

---

## Building from source

```bash
git clone https://github.com/liquid-releasing/forgeassembler
cd forgeassembler
pip install -r requirements.txt
pip install -r requirements-desktop.txt
python forgeassembler.py
```

`ffmpeg` is included automatically via the `imageio-ffmpeg` pip package — no system install required.

## License

ForgeAssembler's own source code is released under the [MIT License](LICENSE).

Packaged releases bundle third-party software that retains its own license. See [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).

**ForgeAssembler™** and **Liquid Releasing™** are trademarks of Liquid Releasing.

---

*© 2026 [Liquid Releasing](https://github.com/liquid-releasing). Written by human and Claude AI.*
