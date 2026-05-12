from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
from typing import Any

from .common import DEFAULT_RCLONE_PATH
from .rclone_backend import RcloneError, detect_rclone, list_remotes

OAUTH_TIMEOUT_SECONDS = 600
QUERY_TIMEOUT_SECONDS = 30


def add_drive_remote(
    name: str,
    scope: str = "drive",
    interactive: bool = False,
    path: str = DEFAULT_RCLONE_PATH,
) -> str:
    _validate_name(name)
    _ensure_unique(name, path)
    backup = _backup_config(path)
    command = build_add_remote_command(name, scope=scope, path=path)
    output = _spawn(command, interactive=interactive)
    return _format_result(output, backup)


def build_add_remote_command(
    name: str,
    scope: str = "drive",
    path: str = DEFAULT_RCLONE_PATH,
) -> list[str]:
    exe = detect_rclone(path)
    return [exe, "config", "create", name, "drive", f"scope={scope}", "config_is_local=true"]


def _validate_name(name: str) -> None:
    if not name or not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        raise ValueError("Nombre de remote inválido (solo letras, números, guion y guion bajo)")


def _ensure_unique(name: str, path: str) -> None:
    if name in list_remotes(path):
        raise RcloneError(
            f"Ya existe un remote llamado '{name}'. Elegí otro nombre o eliminá el existente con: rclone config delete {name}"
        )


def _backup_config(path: str) -> pathlib.Path | None:
    config_path = _rclone_config_path(path)
    if not config_path or not config_path.exists():
        return None
    backup = config_path.with_suffix(config_path.suffix + ".bak")
    shutil.copy2(config_path, backup)
    return backup


def _rclone_config_path(path: str) -> pathlib.Path | None:
    exe = detect_rclone(path)
    cp = subprocess.run([exe, "config", "file"], capture_output=True, text=True, timeout=10)
    if cp.returncode != 0:
        return None
    for line in cp.stdout.splitlines():
        candidate = pathlib.Path(line.strip())
        if candidate.is_absolute():
            return candidate
    return None


def _format_result(output: str, backup: pathlib.Path | None) -> str:
    if backup is None:
        return output
    return f"{output}\nBackup del config previo: {backup}"


def list_shared_drives(name: str, path: str = DEFAULT_RCLONE_PATH) -> list[dict[str, str]]:
    exe = detect_rclone(path)
    cp = subprocess.run(
        [exe, "backend", "drives", f"{name}:"],
        capture_output=True, text=True, timeout=QUERY_TIMEOUT_SECONDS,
    )
    if cp.returncode != 0:
        raise RcloneError((cp.stderr or "no pude listar Shared Drives").strip())
    return _parse_shared_drives(cp.stdout)


def _parse_shared_drives(raw: str) -> list[dict[str, str]]:
    raw = raw.strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [{"id": str(d.get("id", "")), "name": str(d.get("name", ""))} for d in data if d.get("id")]


def set_shared_drive(name: str, drive_id: str, path: str = DEFAULT_RCLONE_PATH) -> None:
    _validate_name(name)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", drive_id):
        raise ValueError("ID de Shared Drive inválido")
    exe = detect_rclone(path)
    cp = subprocess.run(
        [exe, "config", "update", name, f"team_drive={drive_id}"],
        capture_output=True, text=True, timeout=QUERY_TIMEOUT_SECONDS,
    )
    if cp.returncode != 0:
        raise RcloneError((cp.stderr or "no pude actualizar el remote").strip())


def clear_shared_drive(name: str, path: str = DEFAULT_RCLONE_PATH) -> None:
    _validate_name(name)
    exe = detect_rclone(path)
    subprocess.run(
        [exe, "config", "update", name, "team_drive="],
        capture_output=True, text=True, timeout=QUERY_TIMEOUT_SECONDS,
    )


def _spawn(command: list[str], interactive: bool) -> str:
    if interactive:
        cp = subprocess.run(command, timeout=OAUTH_TIMEOUT_SECONDS)
        if cp.returncode != 0:
            raise RcloneError(f"rclone config create falló (exit {cp.returncode})")
        return ""
    cp = subprocess.run(command, capture_output=True, text=True, timeout=OAUTH_TIMEOUT_SECONDS)
    if cp.returncode != 0:
        raise RcloneError((cp.stderr or "rclone config create falló").strip())
    return (cp.stdout or "") + (cp.stderr or "")
