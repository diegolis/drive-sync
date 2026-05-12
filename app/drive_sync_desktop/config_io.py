from __future__ import annotations

import json
from pathlib import Path

from .storage import find_job_by_name, init_db, upsert_job


def import_config(path: str) -> int:
    init_db()
    data = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    jobs = data.get("jobs", [])
    for entry in jobs:
        _import_one(entry)
    return len(jobs)


def _import_one(entry: dict) -> None:
    payload = _payload_from_json(entry)
    existing = find_job_by_name(payload["name"])
    if existing:
        payload["id"] = existing
    upsert_job(payload)


def _payload_from_json(entry: dict) -> dict:
    return {
        "name": entry["name"],
        "local_path": entry["localPath"],
        "remote_name": entry["remote"],
        "remote_path": entry["remotePath"],
        "mode": entry.get("mode", "copy"),
        "interval_minutes": int(entry.get("scheduleMinutes", 15)),
        "auto_sync": bool(entry.get("autoSync", False)),
        "dry_run_required": bool(entry.get("dryRunRequired", True)),
        "excludes": "\n".join(entry.get("exclude", [])),
    }
