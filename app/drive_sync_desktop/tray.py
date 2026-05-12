from __future__ import annotations

import fcntl
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pystray
from PIL import Image, ImageDraw

from . import service_control
from .common import runtime_dir
from .storage import init_db, list_jobs

POLL_SECONDS = 5
ICON_SIZE = 64
STATE_COLORS = {
    "off": (128, 128, 128),
    "ok": (86, 211, 155),
    "warn": (255, 204, 102),
    "error": (255, 125, 125),
}
STATE_LABELS = {
    "off": "Drive Sync — agente apagado",
    "ok": "Drive Sync — todo OK",
    "warn": "Drive Sync — alguna sync necesita atención",
    "error": "Drive Sync — error en alguna sync",
}


_LOCK_HANDLE = None
_LAST_STATE = "off"


def main() -> None:
    if not _acquire_lock():
        print("[tray] otra instancia ya está corriendo, salgo.", file=sys.stderr)
        return
    init_db()
    icon = pystray.Icon(
        "drive-sync-desktop",
        icon=_render("off"),
        title=STATE_LABELS["off"],
        menu=_build_menu(),
    )
    threading.Thread(target=_poll_loop, args=(icon,), daemon=True).start()
    icon.run()


def _agent_is_active() -> bool:
    return _LAST_STATE != "off"


def _acquire_lock() -> bool:
    global _LOCK_HANDLE
    lock_path = runtime_dir() / "tray.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "w", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return False
    _LOCK_HANDLE = handle
    return True


def _build_menu() -> pystray.Menu:
    return pystray.Menu(
        pystray.MenuItem("Abrir Drive Sync", _open_app, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Activar agente", _enable_agent, visible=lambda _: not _agent_is_active()),
        pystray.MenuItem("Desactivar agente", _disable_agent, visible=lambda _: _agent_is_active()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Salir", _quit),
    )


def _open_app(icon, item) -> None:
    binary = shutil.which("drive-sync-desktop") or str(Path.home() / ".local" / "bin" / "drive-sync-desktop")
    subprocess.Popen([binary], start_new_session=True)


def _enable_agent(icon, item) -> None:
    _safe(service_control.enable)
    _refresh_now(icon)


def _disable_agent(icon, item) -> None:
    _safe(service_control.disable)
    _refresh_now(icon)


def _refresh_now(icon) -> None:
    global _LAST_STATE
    _LAST_STATE = current_state()
    icon.icon = _render(_LAST_STATE)
    icon.title = STATE_LABELS[_LAST_STATE]
    icon.update_menu()


def _safe(fn) -> None:
    try:
        fn()
    except Exception:
        pass


def _quit(icon, item) -> None:
    icon.stop()


def _poll_loop(icon) -> None:
    global _LAST_STATE
    while True:
        try:
            new_state = current_state()
            if new_state != _LAST_STATE:
                _LAST_STATE = new_state
                icon.icon = _render(new_state)
                icon.title = STATE_LABELS[new_state]
                icon.update_menu()
        except Exception:
            pass
        time.sleep(POLL_SECONDS)


def current_state() -> str:
    if not service_control.status().get("active"):
        return "off"
    return _classify_jobs(list_jobs())


def _classify_jobs(jobs: list[dict]) -> str:
    if any(j.get("last_status") == "error" for j in jobs):
        return "error"
    if any(j.get("mode") == "bisync" for j in jobs) and any(j.get("last_status") is None for j in jobs):
        return "warn"
    return "ok"


def _render(state: str) -> Image.Image:
    img = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    r, g, b = STATE_COLORS[state]
    draw.ellipse((4, 4, ICON_SIZE - 4, ICON_SIZE - 4), fill=(r, g, b, 255))
    cx, cy = ICON_SIZE // 2, ICON_SIZE // 2
    draw.polygon([(cx - 12, cy + 4), (cx, cy - 10), (cx + 12, cy + 4)], fill=(255, 255, 255, 255))
    draw.polygon([(cx - 12, cy - 4), (cx, cy + 10), (cx + 12, cy - 4)], fill=(255, 255, 255, 180))
    return img
