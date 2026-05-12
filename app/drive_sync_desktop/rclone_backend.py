from __future__ import annotations

import json
import os
import pathlib
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from .common import DEFAULT_RCLONE_PATH, log_dir

DEFAULT_TIMEOUT_SECONDS = int(os.environ.get("RCLONE_TIMEOUT_SECONDS", "21600"))


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
    return _classify_remotes(data)


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


def _classify_remotes(data: dict) -> list[dict]:
    out = []
    for name, info in data.items():
        if info.get("type") != "drive":
            continue
        team = (info.get("team_drive") or "").strip()
        out.append({
            "name": name,
            "kind": "shared" if team else "personal",
            "label": "Shared Drive" if team else "Mi Drive",
        })
    return out


def _exclude_args(excludes: str | None) -> list[str]:
    patterns = [p.strip() for p in (excludes or "").splitlines() if p.strip()]
    args: list[str] = []
    for pattern in patterns:
        args.extend(["--exclude", pattern])
    return args


def _build_command(
    job: dict,
    dry_run: bool = False,
    resync: bool = False,
    path: str = DEFAULT_RCLONE_PATH,
) -> list[str]:
    exe = detect_rclone(path)
    target = f"{job['remote_name']}:{job['remote_path'].lstrip('/')}"
    command = [exe, job["mode"], job["local_path"], target, "-v", "--stats=1s"]
    if dry_run:
        command.append("--dry-run")
    if job["mode"] == "bisync":
        if resync:
            command.append("--resync")
        else:
            command.extend(["--resilient", "--recover"])
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


def summarize(result: CommandResult) -> str:
    lines = _meaningful_lines((result.stdout or "") + "\n" + (result.stderr or ""))
    errors = [l for l in lines if "error" in l.lower() or "aborted" in l.lower()]
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
    if resync and job["mode"] == "bisync":
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
