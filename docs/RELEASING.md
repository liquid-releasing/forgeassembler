# Releasing

ForgeAssembler ships as a Tauri desktop app with a PyInstaller-frozen Python
backend inside it. One tag builds and publishes the whole thing.

## What a release is made of

```text
ForgeAssembler.exe            the Tauri shell (Rust + the React UI)
  resources/forge-cli/        cli.py + forgeassembler_core, frozen
    forge-cli.exe             what the Rust side invokes, once per command
    _internal/                the Python runtime, numpy, matplotlib, Pillow
      imageio_ffmpeg/         and ffmpeg itself
```

The app shells out to `forge-cli` for every operation, so the freeze is not a
convenience — it *is* the backend. Nothing else needs installing on the user's
machine.

**ffmpeg rides inside the freeze**, via imageio-ffmpeg. ForgeAssembler never
shells `ffprobe` — `forgeassembler_core/probe.py` parses ffmpeg's own stderr
precisely because imageio-ffmpeg ships ffmpeg alone — so unlike the
FunscriptForge pipeline there is no second binary to source per platform and
no GPL build to redistribute (imageio-ffmpeg's is LGPL).

Measured on a local build of `forge-cli.spec`: **201 MB** for the frozen
onedir.

## Cutting one

```bash
python scripts/bump_version.py 0.1.1-alpha    # then commit
git tag v0.1.1-alpha && git push origin v0.1.1-alpha
```

`bump_version.py` writes the version to the four files that must agree and
handles the one that must not: `tauri.conf.json` gets the version **stripped**
of its suffix, because the MSI bundler refuses a non-numeric pre-release
identifier. `--check` verifies agreement and runs in CI before the build.

The tag fires `.github/workflows/release.yml`, which:

1. freezes `forge-cli` and **smoke-tests the frozen binary** (see below);
2. runs pytest and vitest — a release does not get to skip the suite;
3. checks the version strings agree;
4. builds the Tauri bundle with the `tauri.release.conf.json` overlay, which
   is what maps `resources/forge-cli` into the installer;
5. publishes `.msi` + `.exe` to **forgeassembler-releases** as a
   **prerelease**, and dispatches `release-published` at
   **forgeassembler-web**, whose `sync-version.yml` rewrites
   `latest-version.json` — the site's version badge updates itself.

`workflow_dispatch` runs everything except the publish, and stamps the build
`0.1.1-alpha+dev.<sha>` in the UI so a test build can never be mistaken for a
release.

## Why the smoke test is not just `--version`

A PyInstaller freeze fails at **runtime**, in places a version check never
reaches. FunscriptForge once shipped a build with no `yaml` module at all: its
smoke command never touched YAML, so CI was green and Export, Import, Events
and Polish all died in the user's hands.

So CI runs a real forge through the frozen binary and asserts the files it
should have produced:

| Check | What would otherwise ship broken |
|---|---|
| `probe` on a real 1s clip | ffmpeg missing from the freeze |
| `forge --no-video` writes `smoke.forge` | the bundle writer, the joiner registry |
| …and `smoke.heatmap.png` | matplotlib's `mpl-data`, Pillow's plugins |
| `detect` / `validate` / `preview` / `thumbnail` / `import-forge` / `encoder` | every remaining command the Rust bridge calls |

`scripts/ci_smoke_project.py` builds the two-clip project those run against.
It deliberately includes an e-stim and an electrode channel, so the
per-device output folders are exercised rather than one flat name.

## Promoting a build

Releases publish as prereleases on purpose: GitHub keeps prereleases out of
`releases/latest`, and the website's download buttons point at
`releases/latest/download/`. A normal release would put new binaries in front
of every visitor the moment CI finished.

```bash
gh release edit v0.1.1-alpha \
  --repo liquid-releasing/forgeassembler-releases \
  --prerelease=false --latest
```

⚠️ **Before promoting the first Tauri build**, fix the download buttons in
`forgeassembler-web/index.html`. They still name the retired Streamlit
artifacts (`ForgeAssembler-windows.zip`, `-macos.zip`, `-linux.tar.gz`); the
Tauri pipeline produces `ForgeAssembler-Setup-windows.msi` and `-windows.exe`
only. Promote without fixing them and every button 404s.

## Platforms

**Windows only, for now.** It is the dogfood platform and the only one this
app has been run on. The macOS and Linux jobs are a straight port of
FunscriptForge's — same shape, one job each — when there is a reason to want
them.
