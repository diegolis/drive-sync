from __future__ import annotations

import pathlib
import sys
from typing import Any, Callable

from . import service_control
from .agent import run_one
from .common import ensure_dirs
from .onboarding import add_drive_remote, list_shared_drives, set_shared_drive
from .rclone_backend import list_remote_folders, list_remotes, list_remotes_detailed, make_remote_folder
from .storage import (
    delete_job,
    find_duplicate_target,
    get_job,
    has_baseline_run,
    init_db,
    list_jobs,
    list_runs,
    upsert_job,
)

FolderPicker = Callable[[], str]


def _log_swallowed(where: str, exc: BaseException) -> None:
    print(f"[bridge:{where}] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)


class Bridge:
    def __init__(self, folder_picker: FolderPicker | None = None) -> None:
        ensure_dirs()
        init_db()
        self._folder_picker = folder_picker

    def set_folder_picker(self, picker: FolderPicker) -> None:
        self._folder_picker = picker

    def list_jobs(self) -> list[dict[str, Any]]:
        jobs = list_jobs()
        for job in jobs:
            job["needs_baseline"] = not has_baseline_run(int(job["id"]))
        return jobs

    def get_job(self, job_id: int) -> dict[str, Any] | None:
        return get_job(int(job_id))

    def list_runs(self, job_id: int) -> list[dict[str, Any]]:
        return list_runs(int(job_id))

    def list_remotes(self) -> list[str]:
        try:
            return list_remotes()
        except Exception as exc:
            _log_swallowed("list_remotes", exc)
            return []

    def list_remotes_detailed(self) -> list[dict[str, Any]]:
        try:
            return list_remotes_detailed()
        except Exception as exc:
            _log_swallowed("list_remotes_detailed", exc)
            return []

    def list_remote_folders(self, remote_name: str, path: str = "") -> list[str]:
        try:
            return list_remote_folders(remote_name, path)
        except Exception as exc:
            _log_swallowed("list_remote_folders", exc)
            return []

    def make_remote_folder(self, remote_name: str, path: str) -> None:
        make_remote_folder(remote_name, path)

    def log(self, payload: dict[str, Any]) -> None:
        import sys
        print(f"[JS] {payload}", file=sys.stderr, flush=True)

    def save_job(self, payload: dict[str, Any]) -> int:
        validated = _validate_payload(_normalize_payload(payload))
        _ensure_unique_target(validated)
        return upsert_job(validated)

    def delete_job(self, job_id: int) -> None:
        delete_job(int(job_id))

    def run(self, job_id: int, dry_run: bool = False, resync: bool = False) -> dict[str, Any]:
        job = get_job(int(job_id))
        if not job:
            return {"ok": False, "summary": "Job does not exist"}
        if not resync and not has_baseline_run(int(job_id)):
            # First run: initialize the baseline with a non-destructive merge
            # of both sides instead of failing.
            resync = True
        ok, summary = run_one(int(job_id), dry_run=bool(dry_run), resync=bool(resync))
        return {"ok": ok, "summary": summary, "resync": bool(resync)}

    def connect_drive(self, name: str | None = None) -> dict[str, Any]:
        final_name = (name or "").strip() or _generate_remote_name()
        output = add_drive_remote(final_name, interactive=False)
        return {
            "name": final_name,
            "output": output,
            "shared_drives": _safe_list_shared(final_name),
        }

    def select_shared_drive(self, name: str, drive_id: str) -> None:
        set_shared_drive(name, drive_id)

    def pick_local_path(self) -> str:
        if not self._folder_picker:
            return ""
        return self._folder_picker() or ""

    def agent_status(self) -> dict[str, Any]:
        return service_control.status()

    def agent_enable(self) -> dict[str, Any]:
        service_control.enable()
        return service_control.status()

    def agent_disable(self) -> dict[str, Any]:
        service_control.disable()
        return service_control.status()


def _normalize_payload(p: dict[str, Any]) -> dict[str, Any]:
    local = (p.get("local_path") or "").strip()
    raw_id = p.get("id")
    return {
        "id": int(raw_id) if raw_id else None,
        "name": (p.get("name") or "").strip() or _default_name(local),
        "local_path": local,
        "remote_name": (p.get("remote_name") or "").strip(),
        "remote_path": (p.get("remote_path") or "").strip().strip("/"),
        "interval_minutes": int(p.get("interval_minutes") or 15),
        "auto_sync": bool(p.get("auto_sync")),
        "excludes": p.get("excludes") or "",
    }


def _default_name(local: str) -> str:
    if not local:
        return ""
    return pathlib.Path(local.rstrip("/")).name or local


def _generate_remote_name() -> str:
    try:
        existing = set(list_remotes())
    except Exception as exc:
        _log_swallowed("generate_remote_name.list_remotes", exc)
        existing = set()
    if "gdrive" not in existing:
        return "gdrive"
    n = 2
    while f"gdrive{n}" in existing:
        n += 1
    return f"gdrive{n}"


def _validate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    missing = [k for k in ("name", "local_path", "remote_name") if not payload.get(k)]
    if missing:
        raise ValueError(f"Missing fields: {', '.join(missing)}")
    if not payload.get("remote_path") and not _remote_is_shared_drive(payload["remote_name"]):
        # A Shared Drive root is itself a project folder, so it's a valid
        # target; the root of My Drive (everything the account owns) is not.
        raise ValueError(
            "Pick a folder in Drive for this sync. Syncing against the entire "
            "My Drive root is not allowed."
        )
    return payload


def _remote_is_shared_drive(remote_name: str) -> bool:
    try:
        remotes = list_remotes_detailed()
    except Exception as exc:
        _log_swallowed("remote_is_shared_drive", exc)
        return False
    return any(r.get("name") == remote_name and r.get("kind") == "shared" for r in remotes)


def _safe_list_shared(name: str) -> list[dict[str, str]]:
    try:
        return list_shared_drives(name)
    except Exception as exc:
        _log_swallowed("list_shared_drives", exc)
        return []


def _ensure_unique_target(payload: dict[str, Any]) -> None:
    duplicate = find_duplicate_target(
        payload["local_path"],
        payload["remote_name"],
        payload["remote_path"],
        exclude_id=payload.get("id"),
    )
    if duplicate is not None:
        raise ValueError(
            "Another sync already targets the same local folder and Drive destination. "
            "Delete it first or change one of the paths."
        )
