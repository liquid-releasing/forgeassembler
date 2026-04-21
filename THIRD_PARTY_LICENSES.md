# Third-Party Licenses

ForgeAssembler's own source code is released under the [MIT License](LICENSE).

Packaged releases of ForgeAssembler bundle third-party software that retains its own license. This file lists each dependency, its license, and where to find the full license text.

---

## Bundled binaries

### FFmpeg

- **License:** LGPL 2.1 (or GPL 2 if built with GPL-licensed codecs)
- **Project:** [ffmpeg.org](https://ffmpeg.org)
- **License text:** [ffmpeg.org/legal.html](https://www.ffmpeg.org/legal.html)
- **Used for:** video/audio concat, encoding, filtering (fades, overlays, drawtext, loudnorm), and heatmap compositing.
- **Packaged releases** include a copy of the applicable ffmpeg license alongside the `ffmpeg` executable in the distribution.

## Python dependencies

### Streamlit

- **License:** Apache License 2.0
- **Project:** [streamlit.io](https://streamlit.io)
- **License text:** [github.com/streamlit/streamlit/blob/develop/LICENSE](https://github.com/streamlit/streamlit/blob/develop/LICENSE)
- **Used for:** the application UI framework.

### pywebview

- **License:** BSD 3-Clause
- **Project:** [pywebview.flowrl.com](https://pywebview.flowrl.com)
- **License text:** [github.com/r0x0r/pywebview/blob/master/LICENSE](https://github.com/r0x0r/pywebview/blob/master/LICENSE)
- **Used for:** the native desktop window wrapper around the Streamlit UI and the HTTP bridge for native folder/file pickers.

### imageio-ffmpeg

- **License:** BSD 2-Clause
- **Project:** [github.com/imageio/imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg)
- **Used for:** bundling a platform-specific ffmpeg binary with the release so users don't need to install ffmpeg separately.

### Pillow (PIL Fork)

- **License:** MIT-CMU (HPND)
- **Project:** [python-pillow.org](https://python-pillow.org)
- **License text:** [github.com/python-pillow/Pillow/blob/main/LICENSE](https://github.com/python-pillow/Pillow/blob/main/LICENSE)
- **Used for:** reading image overlay PNGs (alpha channels) and rendering heatmap visualizations.

### NumPy

- **License:** BSD 3-Clause
- **Project:** [numpy.org](https://numpy.org)
- **License text:** [github.com/numpy/numpy/blob/main/LICENSE.txt](https://github.com/numpy/numpy/blob/main/LICENSE.txt)
- **Used for:** numerical processing when building heatmaps and funscript track math.

### Matplotlib

- **License:** Matplotlib License (BSD-compatible, PSF-derived)
- **Project:** [matplotlib.org](https://matplotlib.org)
- **License text:** [matplotlib.org/stable/users/project/license.html](https://matplotlib.org/stable/users/project/license.html)
- **Used for:** rendering funscript heatmap images for the combined output.

### requests

- **License:** Apache License 2.0
- **Project:** [requests.readthedocs.io](https://requests.readthedocs.io)
- **Used for:** optional HTTP fetches (reserved for features that may pull online assets).

### psutil

- **License:** BSD 3-Clause
- **Project:** [github.com/giampaolo/psutil](https://github.com/giampaolo/psutil)
- **Used for:** process lifecycle management in the desktop launcher.

### PyInstaller

- **License:** GPL 2 with an explicit exception permitting the PyInstaller bootloader to be used with any license, including proprietary.
- **Project:** [pyinstaller.org](https://pyinstaller.org)
- **License text:** [github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt](https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt)
- **Used for:** packaging the Python application into single-folder native bundles for Windows, macOS, and Linux.

## Transitive dependencies

ForgeAssembler's packaged releases also bundle many transitive dependencies of the packages listed above (altair, pyarrow, tornado, click, rich, watchdog, and others pulled in by Streamlit). These retain their own licenses; see the `dist-info` directories alongside the executable for the full set.
