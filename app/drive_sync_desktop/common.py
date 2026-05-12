from __future__ import annotations

import os
import pathlib
import platform
from dataclasses import dataclass

from . import APP_NAME, __version__

APP_ID = "drive-sync-desktop"
DEFAULT_RCLONE_PATH = os.environ.get("RCLONE_PATH", "rclone")


def _home() -> pathlib.Path:
    return pathlib.Path.home()


def config_dir() -> pathlib.Path:
    if os.environ.get("XDG_CONFIG_HOME"):
        return pathlib.Path(os.environ["XDG_CONFIG_HOME"]) / APP_ID
    return _home() / ".config" / APP_ID


def data_dir() -> pathlib.Path:
    if os.environ.get("XDG_DATA_HOME"):
        return pathlib.Path(os.environ["XDG_DATA_HOME"]) / APP_ID
    return _home() / ".local" / "share" / APP_ID


def log_dir() -> pathlib.Path:
    return data_dir() / "logs"


def runtime_dir() -> pathlib.Path:
    base = pathlib.Path(os.environ.get("XDG_RUNTIME_DIR", str(data_dir() / "run")))
    return base / APP_ID


def db_path() -> pathlib.Path:
    return data_dir() / "app.db"


def ensure_dirs() -> None:
    for path in [config_dir(), data_dir(), log_dir(), runtime_dir()]:
        path.mkdir(parents=True, exist_ok=True)
        try:
            path.chmod(0o700)
        except OSError:
            pass


@dataclass(slots=True)
class AppInfo:
    name: str = APP_NAME
    version: str = __version__
    system: str = platform.system()
    release: str = platform.release()
