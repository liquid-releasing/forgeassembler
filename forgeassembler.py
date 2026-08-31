# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""ForgeAssembler desktop launcher.

Dual-mode entry:
  * dev:     `python forgeassembler.py`   — spawns streamlit as a subprocess.
  * bundled: the PyInstaller exe re-executes itself with the sentinel
             argument to run streamlit in the same process.

The launcher opens a PyWebView window pointing at the local Streamlit
server and also runs a small HTTP bridge so the UI can request a native
folder picker.
"""

from __future__ import annotations

import http.server
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
from pathlib import Path

# Sentinel used by the bundled exe to re-enter and run streamlit in-process.
RUN_STREAMLIT_FLAG = "--run-streamlit"
APP_TITLE = "ForgeAssembler"
APP_WIDTH = 1200
APP_HEIGHT = 820
STREAMLIT_HOST = "127.0.0.1"

_here = Path(__file__).resolve().parent


# ── Streamlit runner (bundled path) ───────────────────────────────────
def _run_streamlit_in_process(port: int, script: str) -> None:
    """Run Streamlit inside this process. Used by the bundled exe re-exec."""
    import sys as _sys

    # In a PyInstaller bundle, streamlit can't detect that it's "pip-installed",
    # so it defaults developmentMode=True — which conflicts with --server.port.
    # Force it off.
    os.environ["STREAMLIT_GLOBAL_DEVELOPMENT_MODE"] = "false"

    _sys.argv = [
        "streamlit",
        "run",
        script,
        "--global.developmentMode=false",
        f"--server.port={port}",
        f"--server.address={STREAMLIT_HOST}",
        "--server.headless=true",
        "--server.fileWatcherType=none",
        "--browser.gatherUsageStats=false",
        "--client.toolbarMode=minimal",
    ]
    from streamlit.web.cli import main as streamlit_main  # noqa: PLC0415
    streamlit_main()


# ── Streamlit runner (dev path) ───────────────────────────────────────
def _spawn_streamlit_dev(port: int, script: str) -> subprocess.Popen:
    env = dict(os.environ)
    env["FORGEASSEMBLER_DESKTOP"] = "1"
    env["STREAMLIT_SERVER_HEADLESS"] = "true"
    env["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] = "none"
    env["STREAMLIT_CLIENT_TOOLBAR_MODE"] = "minimal"
    env["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    cmd = [
        sys.executable,
        "-m", "streamlit", "run", script,
        f"--server.port={port}",
        f"--server.address={STREAMLIT_HOST}",
    ]
    return subprocess.Popen(cmd, cwd=str(_here), env=env)


def _free_port(preferred: int = 0) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((STREAMLIT_HOST, preferred))
        return s.getsockname()[1]


def _wait_for_server(port: int, timeout_s: float = 30.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with socket.create_connection((STREAMLIT_HOST, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


# ── Bridge HTTP server (native folder / file picker) ──────────────────
class _BridgeHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:  # silence default logs
        return

    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        import webview  # noqa: PLC0415

        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        initial = params.get("initial", [""])[0]

        windows = webview.windows
        if not windows:
            self._reply(503, "")
            return

        # Only supply `directory` to pywebview when we have a real path;
        # passing None raises `_path_exists` deep inside pywebview.
        kwargs: dict = {}
        if initial:
            kwargs["directory"] = initial

        if parsed.path == "/pick-folder":
            result = windows[0].create_file_dialog(
                webview.FOLDER_DIALOG,
                **kwargs,
            )
        elif parsed.path == "/pick-file":
            filters_raw = params.get("filter", [])
            if filters_raw:
                kwargs["file_types"] = tuple(filters_raw)
            result = windows[0].create_file_dialog(
                webview.OPEN_DIALOG,
                **kwargs,
            )
        else:
            self._reply(404, "not found")
            return

        if result:
            path = result[0] if isinstance(result, (list, tuple)) else result
            self._reply(200, str(path))
        else:
            self._reply(204, "")

    def _reply(self, status: int, body: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        if body:
            self.wfile.write(body.encode("utf-8"))


def _start_bridge_server(port: int) -> None:
    server = http.server.ThreadingHTTPServer((STREAMLIT_HOST, port), _BridgeHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()


# ── Main ──────────────────────────────────────────────────────────────
def main() -> int:
    # Bundled self-re-exec path
    if len(sys.argv) > 1 and sys.argv[1] == RUN_STREAMLIT_FLAG:
        port = int(sys.argv[2])
        script = sys.argv[3]
        _run_streamlit_in_process(port, script)
        return 0

    streamlit_port = _free_port()
    bridge_port = _free_port()

    os.environ["FORGEASSEMBLER_DESKTOP"] = "1"
    os.environ["FORGEASSEMBLER_BRIDGE_PORT"] = str(bridge_port)

    ui_script = str(_here / "ui.py")

    # Launch Streamlit
    if getattr(sys, "frozen", False):
        # Bundled: re-exec self with the sentinel flag as a subprocess
        env = dict(os.environ)
        proc = subprocess.Popen(
            [sys.executable, RUN_STREAMLIT_FLAG, str(streamlit_port), ui_script],
            env=env,
        )
    else:
        proc = _spawn_streamlit_dev(streamlit_port, ui_script)

    if not _wait_for_server(streamlit_port, timeout_s=30.0):
        proc.terminate()
        print("ERROR: Streamlit did not start within 30 seconds.", file=sys.stderr)
        return 1

    # PyWebView window + bridge
    import webview  # noqa: PLC0415

    webview.create_window(
        APP_TITLE,
        url=f"http://{STREAMLIT_HOST}:{streamlit_port}",
        width=APP_WIDTH,
        height=APP_HEIGHT,
        resizable=True,
        text_select=True,
    )

    def _on_start() -> None:
        _start_bridge_server(bridge_port)

    # Point pywebview at the FA icon; without it the window/taskbar
    # falls back to the Python interpreter's icon when running from
    # source. Per-platform format: Windows pywebview routes through
    # .NET System.Drawing.Icon, which insists on a real .ico (a PNG
    # raises 'Argument picture must be a picture that can be used as
    # an Icon'). macOS reads the bundle's .icns at the BUNDLE level
    # so `icon=` here is a no-op there. Linux pywebview is happy with
    # PNG.
    if sys.platform == "win32":
        icon_path = _here / "media" / "forgeassembler.ico"
    else:
        icon_path = _here / "media" / "forgeassembler_icon.png"
    icon_arg = str(icon_path) if icon_path.exists() else None

    # Native window-level Help menu. Each item opens a URL in the
    # user's default browser via `webbrowser.open` so the FA window
    # stays on the app. macOS gets full Cocoa menu bar integration;
    # Windows + Linux backend support varies — wrap in try/except so
    # an unsupported backend just renders without a menu instead of
    # crashing the launcher.
    menu_items: list = []
    try:
        import webbrowser  # noqa: PLC0415
        from webview.menu import Menu, MenuAction  # noqa: PLC0415

        def _open(url: str) -> "callable":
            return lambda: webbrowser.open(url)

        menu_items = [
            Menu("Help", [
                MenuAction(
                    "Documentation",
                    _open("https://liquid-releasing.github.io/forgeassembler/"),
                ),
                MenuAction(
                    "Discord (community)",
                    _open("https://discord.gg/UHdJFhEZF"),
                ),
                MenuAction(
                    "GitHub repo",
                    _open("https://github.com/liquid-releasing/forgeassembler"),
                ),
                MenuAction(
                    "Report a bug",
                    _open("https://github.com/liquid-releasing/forgeassembler/issues/new"),
                ),
            ]),
        ]
    except Exception:  # noqa: BLE001
        # Older pywebview / unsupported backend — skip the menu. The
        # in-app Help / About dialog already covers the essentials.
        menu_items = []

    try:
        webview.start(func=_on_start, icon=icon_arg, menu=menu_items)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
