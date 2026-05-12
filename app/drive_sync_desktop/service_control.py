from __future__ import annotations

import subprocess
from typing import Any

UNIT_NAME = "drive-sync-desktop-agent.service"
TIMEOUT_QUERY = 5
TIMEOUT_ACTION = 15


def status() -> dict[str, Any]:
    if not _unit_known():
        return {"available": False, "active": False, "enabled": False}
    return {"available": True, "active": _is_active(), "enabled": _is_enabled()}


def enable() -> None:
    _run(["systemctl", "--user", "enable", "--now", UNIT_NAME])


def disable() -> None:
    _run(["systemctl", "--user", "disable", "--now", UNIT_NAME])


def _unit_known() -> bool:
    try:
        cp = subprocess.run(
            ["systemctl", "--user", "list-unit-files", UNIT_NAME],
            capture_output=True, text=True, timeout=TIMEOUT_QUERY,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return cp.returncode == 0 and UNIT_NAME in cp.stdout


def _is_active() -> bool:
    return _check(["systemctl", "--user", "is-active", "--quiet", UNIT_NAME])


def _is_enabled() -> bool:
    return _check(["systemctl", "--user", "is-enabled", "--quiet", UNIT_NAME])


def _check(cmd: list[str]) -> bool:
    try:
        cp = subprocess.run(cmd, capture_output=True, timeout=TIMEOUT_QUERY)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return cp.returncode == 0


def _run(cmd: list[str]) -> None:
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_ACTION)
    except FileNotFoundError as exc:
        raise RuntimeError("systemctl is not available") from exc
    if cp.returncode != 0:
        raise RuntimeError((cp.stderr or cp.stdout).strip() or f"systemctl failed (exit {cp.returncode})")
