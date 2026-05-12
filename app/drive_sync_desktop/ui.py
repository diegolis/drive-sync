from __future__ import annotations

import os
import pathlib

import webview

from . import __version__
from .bridge import Bridge
from .common import APP_NAME

WINDOW_WIDTH = 1100
WINDOW_HEIGHT = 720
MIN_WIDTH = 880
MIN_HEIGHT = 600


JS_ERROR_HOOK = """
window.addEventListener('error', function(e) {
  try { window.pywebview.api.log({type: 'error', message: e.message, source: e.filename, line: e.lineno, stack: e.error && e.error.stack}); } catch(_) {}
});
window.addEventListener('unhandledrejection', function(e) {
  try { window.pywebview.api.log({type: 'rejection', reason: String(e.reason), stack: e.reason && e.reason.stack}); } catch(_) {}
});
"""


def main() -> None:
    bridge = Bridge()
    window = _create_window(bridge)
    bridge.set_folder_picker(lambda: _pick_folder(window))
    if _debug_enabled():
        window.events.loaded += lambda: window.evaluate_js(JS_ERROR_HOOK)
    webview.start(debug=_debug_enabled())


def _debug_enabled() -> bool:
    return bool(os.environ.get("DRIVE_SYNC_DEBUG"))


def _create_window(bridge: Bridge):
    return webview.create_window(
        title=f"{APP_NAME} {__version__}",
        url=str(_frontend_path()),
        js_api=bridge,
        width=WINDOW_WIDTH,
        height=WINDOW_HEIGHT,
        min_size=(MIN_WIDTH, MIN_HEIGHT),
        background_color="#0b1020",
    )


def _frontend_path() -> pathlib.Path:
    return pathlib.Path(__file__).parent / "frontend" / "index.html"


def _pick_folder(window) -> str:
    result = window.create_file_dialog(webview.FOLDER_DIALOG)
    if not result:
        return ""
    return result[0] if isinstance(result, (list, tuple)) else str(result)
