import json
from pathlib import Path

from drive_sync_desktop import config_io, storage


def _write(path: Path, jobs: list[dict]) -> Path:
    path.write_text(json.dumps({"jobs": jobs}), encoding="utf-8")
    return path


def _entry(name: str = "docs") -> dict:
    return {
        "name": name,
        "localPath": "/tmp/docs",
        "remote": "gdrive",
        "remotePath": "Backups/Docs",
        "mode": "copy",
        "scheduleMinutes": 20,
        "autoSync": True,
        "dryRunRequired": True,
        "exclude": ["*.tmp", "node_modules/**"],
    }


def test_import_creates_job(tmp_path):
    file = _write(tmp_path / "cfg.json", [_entry()])
    count = config_io.import_config(str(file))
    assert count == 1
    job = storage.list_jobs()[0]
    assert job["name"] == "docs"
    assert job["interval_minutes"] == 20
    assert job["auto_sync"] == 1
    assert "*.tmp" in job["excludes"]


def test_import_is_idempotent_by_name(tmp_path):
    file = _write(tmp_path / "cfg.json", [_entry()])
    config_io.import_config(str(file))
    config_io.import_config(str(file))
    jobs = storage.list_jobs()
    assert len(jobs) == 1


def test_import_updates_existing(tmp_path):
    config_io.import_config(str(_write(tmp_path / "a.json", [_entry()])))
    updated = _entry()
    updated["scheduleMinutes"] = 99
    config_io.import_config(str(_write(tmp_path / "b.json", [updated])))
    job = storage.list_jobs()[0]
    assert job["interval_minutes"] == 99
