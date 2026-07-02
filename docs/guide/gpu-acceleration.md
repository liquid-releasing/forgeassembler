# GPU acceleration

ForgeAssembler encodes the final video with your machine's **GPU hardware
encoder** when one is available, and falls back to the **CPU** when it isn't.

!!! tip "A GPU is optional, but recommended"
    You do **not** need a GPU — the CPU encoder (`libx264`) always works and
    produces the same output. But a supported GPU is **faster** and keeps the
    machine **much cooler**: the encode is the one all-cores-pinned stage of a
    forge, and offloading it to the GPU's dedicated encoder block frees the CPU.
    On laptops and thermally-limited machines this is the difference between a
    quiet, cool render and a long, fan-blasting one.

## How it's chosen

Selection is **automatic**. On the first forge of a session ForgeAssembler runs
a sub-second test encode to find the fastest hardware encoder that actually
works on your machine, then reuses it for the rest of the run. If none works, it
uses the CPU.

The CLI prints which encoder it picked:

```
Forging video at 1080p [GPU · NVIDIA NVENC] → …/output/scene.mp4
```

`[CPU · libx264]` means no supported GPU encoder was detected.

## Supported encoders

| Vendor | ForgeAssembler id | ffmpeg encoder | Hardware |
| ------ | ----------------- | -------------- | -------- |
| **NVIDIA** | `nvenc` | `h264_nvenc` | GeForce / RTX / Quadro (NVENC) |
| **Intel** | `qsv` | `h264_qsv` | Arc GPUs and recent iGPUs (Quick Sync) |
| **AMD** | `amf` | `h264_amf` | Radeon (AMF / VCE) |
| **Any (fallback)** | `x264` | `libx264` | CPU — always available |

All produce standard H.264 MP4s. The quality preset (`low` / `medium` / `high`)
maps to each encoder's nearest constant-quality control, so the setting keeps
the same meaning whichever encoder runs.

!!! note "Recommended GPU"
    An **NVIDIA** card with NVENC (GeForce GTX 10-series or newer, any RTX) is
    the best-supported and fastest path. Intel Quick Sync and AMD AMF also work
    when present. Auto-detect prefers NVIDIA → Intel → AMD → CPU.

## Overriding the choice

Set the `FORGEASSEMBLER_ENCODER` environment variable to force a specific
encoder (skips auto-detect):

| Value | Effect |
| ----- | ------ |
| *(unset)* | Auto-detect the best available (default) |
| `nvenc` / `qsv` / `amf` | Force that hardware encoder |
| `x264` (or `cpu`) | Force the CPU encoder |

```bash
# Force the CPU encoder (e.g. to compare quality, or on a flaky driver)
FORGEASSEMBLER_ENCODER=x264 forgeassembler forge project.json
```

## Requirements

The GPU path needs an ffmpeg built with the vendor encoder (the bundled ffmpeg
includes NVENC, Quick Sync, and AMF) **and** a working GPU + up-to-date driver.
If the driver is missing or the encoder can't initialize, the test probe fails
and ForgeAssembler quietly falls back to the CPU — a forge never breaks for lack
of a GPU.
