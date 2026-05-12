from __future__ import annotations

import json
from pathlib import Path

from .storage import find_job_by_name, init_db, upsert_job


class ConfigImportError(ValueError):
    pass


def import_config(path: str) -> int:
    init_db()
    raw = _read(path)
    data = _parse(raw, path)
    jobs = data.get("jobs", [])
    if not isinstance(jobs, list):
        raise ConfigImportError("Expected 'jobs' to be a list")
    for i, entry in enumerate(jobs):
        if not isinstance(entry, dict):
            raise ConfigImportError(f"jobs[{i}] is not an object")
        _import_one(entry, i)
    return len(jobs)


def _read(path: str) -> str:
    try:
        return Path(path).expanduser().read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigImportError(f"File not found: {path}")
    except OSError as exc:
        raise ConfigImportError(f"Could not read {path}: {exc}")


def _parse(raw: str, path: str) -> dict:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigImportError(f"Invalid JSON in {path}: {exc.msg} (line {exc.lineno}, col {exc.colno})")
    if not isinstance(data, dict):
        raise ConfigImportError("Top-level JSON must be an object")
    return data


def _import_one(entry: dict, index: int) -> None:
    payload = _payload_from_json(entry, index)
    existing = find_job_by_name(payload["name"])
    if existing:
        payload["id"] = existing
    upsert_job(payload)


def _payload_from_json(entry: dict, index: int) -> dict:
    name = _require_str(entry, "name", index)
    local_path = _require_str(entry, "localPath", index)
    remote = _require_str(entry, "remote", index)
    excludes = entry.get("exclude", [])
    if not isinstance(excludes, list):
        raise ConfigImportError(f"jobs[{index}].exclude must be a list of strings")
    return {
        "name": name,
        "local_path": local_path,
        "remote_name": remote,
        "remote_path": str(entry.get("remotePath", "")),
        "mode": entry.get("mode", "copy"),
        "interval_minutes": int(entry.get("scheduleMinutes", 15)),
        "auto_sync": bool(entry.get("autoSync", False)),
        "dry_run_required": bool(entry.get("dryRunRequired", True)),
        "excludes": "\n".join(str(x) for x in excludes),
    }


def _require_str(entry: dict, key: str, index: int) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigImportError(f"jobs[{index}].{key} is required and must be a non-empty string")
    return value
