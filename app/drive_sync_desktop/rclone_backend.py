from __future__ import annotations

import json
import os
import pathlib
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from .common import DEFAULT_RCLONE_PATH, log_dir

DEFAULT_TIMEOUT_SECONDS = int(os.environ.get("RCLONE_TIMEOUT_SECONDS", "21600"))
# Abort the sync if it would delete more than this percentage of files on
# either side. Protects against an unmounted/emptied folder wiping the other.
MAX_DELETE_PERCENT = int(os.environ.get("DRIVE_SYNC_MAX_DELETE", "50"))


class RcloneError(RuntimeError):
    pass


@dataclass(slots=True)
class CommandResult:
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    log_path: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


def detect_rclone(path: str = DEFAULT_RCLONE_PATH) -> str:
    resolved = shutil.which(path) or (path if pathlib.Path(path).exists() else "")
    if not resolved:
        raise RcloneError("Could not find rclone in PATH")
    return resolved


def version(path: str = DEFAULT_RCLONE_PATH) -> str:
    exe = detect_rclone(path)
    cp = subprocess.run([exe, "version"], capture_output=True, text=True, timeout=30)
    if cp.returncode != 0:
        raise RcloneError(cp.stderr.strip() or "rclone version failed")
    return cp.stdout.strip()


def list_remotes(path: str = DEFAULT_RCLONE_PATH) -> list[str]:
    exe = detect_rclone(path)
    cp = subprocess.run([exe, "listremotes"], capture_output=True, text=True, timeout=30)
    if cp.returncode != 0:
        raise RcloneError(cp.stderr.strip() or "Could not list remotes")
    return [line.strip().rstrip(":") for line in cp.stdout.splitlines() if line.strip()]


def list_remotes_detailed(path: str = DEFAULT_RCLONE_PATH) -> list[dict]:
    exe = detect_rclone(path)
    cp = subprocess.run([exe, "config", "dump"], capture_output=True, text=True, timeout=30)
    if cp.returncode != 0:
        return []
    try:
        data = json.loads(cp.stdout or "{}")
    except json.JSONDecodeError:
        return []
    return _classify_remotes(data, path)


def list_remote_folders(remote_name: str, path: str = "", rclone_path: str = DEFAULT_RCLONE_PATH) -> list[str]:
    exe = detect_rclone(rclone_path)
    target = f"{remote_name}:{path.lstrip('/')}"
    cp = subprocess.run(
        [exe, "lsf", "--dirs-only", "--max-depth", "1", target],
        capture_output=True, text=True, timeout=30,
    )
    if cp.returncode != 0:
        raise RcloneError(cp.stderr.strip() or "Could not list folders")
    return sorted(line.rstrip("/").strip() for line in cp.stdout.splitlines() if line.strip())


def make_remote_folder(remote_name: str, path: str, rclone_path: str = DEFAULT_RCLONE_PATH) -> None:
    exe = detect_rclone(rclone_path)
    target = f"{remote_name}:{path.lstrip('/')}"
    cp = subprocess.run([exe, "mkdir", target], capture_output=True, text=True, timeout=30)
    if cp.returncode != 0:
        raise RcloneError(cp.stderr.strip() or "Could not create folder")


def _classify_remotes(data: dict, path: str = DEFAULT_RCLONE_PATH) -> list[dict]:
    out = []
    for name, info in data.items():
        if info.get("type") != "drive":
            continue
        team = (info.get("team_drive") or "").strip()
        if team:
            label = _shared_drive_name(name, team, path) or "Shared Drive"
        else:
            label = "My Drive"
        out.append({
            "name": name,
            "kind": "shared" if team else "personal",
            "label": label,
        })
    return out


def _shared_drive_name(remote_name: str, team_id: str, path: str) -> str | None:
    """Resolve the human name of the Shared Drive a remote points to."""
    try:
        exe = detect_rclone(path)
        cp = subprocess.run(
            [exe, "backend", "drives", f"{remote_name}:"],
            capture_output=True, text=True, timeout=15,
        )
        if cp.returncode != 0:
            return None
        for drive in json.loads(cp.stdout or "[]"):
            if drive.get("id") == team_id:
                return (drive.get("name") or "").strip() or None
    except (RcloneError, OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError):
        return None
    return None


def _exclude_args(excludes: str | None) -> list[str]:
    patterns = [p.strip() for p in (excludes or "").splitlines() if p.strip()]
    args: list[str] = []
    for pattern in patterns:
        args.extend(["--exclude", pattern])
    return args


def _cache_dir(path: str = DEFAULT_RCLONE_PATH) -> pathlib.Path | None:
    """Resolve rclone's cache dir, where bisync stores its lock files."""
    try:
        exe = detect_rclone(path)
        cp = subprocess.run([exe, "config", "paths"], capture_output=True, text=True, timeout=30)
    except (RcloneError, OSError, subprocess.SubprocessError):
        return None
    for line in cp.stdout.splitlines():
        if line.lower().startswith("cache dir:"):
            return pathlib.Path(line.split(":", 1)[1].strip())
    return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but is owned by another user — treat as alive.
        return True
    except OSError:
        return True
    return True


def clear_stale_bisync_locks(path: str = DEFAULT_RCLONE_PATH) -> list[str]:
    """Remove bisync lock files whose owning process is no longer running.

    A bisync run interrupted by a crash or reboot leaves a lock file behind
    that rclone refuses to override, blocking every later sync of the same
    paths. The lock records the PID that created it; if that PID is dead, the
    lock is orphaned and safe to delete.

    Returns the names of the lock files that were removed.
    """
    cache = _cache_dir(path)
    if cache is None:
        return []
    bisync_dir = cache / "bisync"
    if not bisync_dir.is_dir():
        return []
    removed: list[str] = []
    for lock in bisync_dir.glob("*.lck"):
        try:
            info = json.loads(lock.read_text(encoding="utf-8"))
            pid = int(info.get("PID", 0))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if pid > 0 and _pid_alive(pid):
            continue
        try:
            lock.unlink()
            removed.append(lock.name)
        except OSError:
            continue
    return removed


def _build_command(
    job: dict,
    dry_run: bool = False,
    resync: bool = False,
    path: str = DEFAULT_RCLONE_PATH,
) -> list[str]:
    exe = detect_rclone(path)
    target = f"{job['remote_name']}:{job['remote_path'].lstrip('/')}"
    command = [
        exe, "bisync", job["local_path"], target,
        "-v", "--stats=1s", f"--max-delete={MAX_DELETE_PERCENT}",
    ]
    if dry_run:
        command.append("--dry-run")
    if resync:
        # Baseline init: merges both sides, never deletes anything.
        command.append("--resync")
    else:
        # On conflict the newer file wins; the older copy is kept renamed,
        # so neither side can silently overwrite data.
        command.extend(["--resilient", "--recover", "--conflict-resolve", "newer"])
    command.extend(_exclude_args(job.get("excludes")))
    return command


def _run(command: Sequence[str], run_label: str, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> CommandResult:
    log_dir().mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = log_dir() / f"{run_label}-{stamp}.log"
    return _capture(list(command), str(log_path), timeout)


def _capture(command: list[str], log_path: str, timeout: int) -> CommandResult:
    try:
        cp = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        stdout, stderr, code = cp.stdout, cp.stderr, cp.returncode
    except subprocess.TimeoutExpired as exc:
        stdout = _decode(exc.stdout)
        stderr = _decode(exc.stderr) + f"\nTIMEOUT after {timeout}s\n"
        code = 124
    log = pathlib.Path(log_path)
    log.write_text(_combined(stdout, stderr), encoding="utf-8")
    try:
        log.chmod(0o600)
    except OSError:
        pass
    return CommandResult(command, code, stdout, stderr, log_path)


def _decode(value) -> str:
    if value is None:
        return ""
    return value.decode() if isinstance(value, bytes) else value


def _combined(stdout: str, stderr: str) -> str:
    parts = [p for p in [stdout, stderr] if p]
    return "\n".join(parts) if parts else "(no output)\n"


_NOISE = ("bisync is experimental",)
_INFO_KEYWORDS = ("copied", "transferred", "deleted", "renamed", "checks:", "must run", "timeout")
# Word-bounded so the stats line "Errors: 0" or filenames like error_log.txt
# don't get flagged as errors.
_ERROR_RE = re.compile(r"(?i)\berror\b\s*:|\baborted\b|\bcritical\b|safety abort|must run --resync")


def summarize(result: CommandResult) -> str:
    lines = _meaningful_lines((result.stdout or "") + "\n" + (result.stderr or ""))
    errors = [l for l in lines if _ERROR_RE.search(l)]
    info = [l for l in lines if any(k in l.lower() for k in _INFO_KEYWORDS)]
    interesting = errors + info or lines[-8:]
    return "\n".join(interesting[:20]) or ("OK" if result.ok else "Failed with no usable output")


def _meaningful_lines(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(noise in stripped.lower() for noise in _NOISE):
            continue
        out.append(stripped)
    return out


def run_job(
    job: dict,
    dry_run: bool = False,
    resync: bool = False,
    path: str = DEFAULT_RCLONE_PATH,
) -> CommandResult:
    clear_stale_bisync_locks(path)
    if resync:
        _ensure_remote_dir(_remote_target(job), path)
    command = _build_command(job, dry_run=dry_run, resync=resync, path=path)
    label = f"job-{job.get('id', 'adhoc')}-{'dry' if dry_run else 'sync'}"
    return _run(command, label)


def _remote_target(job: dict) -> str:
    return f"{job['remote_name']}:{job['remote_path'].lstrip('/')}"


def _ensure_remote_dir(target: str, path: str) -> None:
    exe = detect_rclone(path)
    subprocess.run([exe, "mkdir", target], capture_output=True, text=True, timeout=30)


def preview_command(
    job: dict,
    dry_run: bool = False,
    resync: bool = False,
    path: str = DEFAULT_RCLONE_PATH,
) -> str:
    return shlex.join(_build_command(job, dry_run=dry_run, resync=resync, path=path))
