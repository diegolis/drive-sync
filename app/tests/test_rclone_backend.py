from dataclasses import replace

import pytest

from drive_sync_desktop import rclone_backend
from drive_sync_desktop.rclone_backend import CommandResult


@pytest.fixture
def fake_rclone(monkeypatch):
    monkeypatch.setattr(rclone_backend, "detect_rclone", lambda path=rclone_backend.DEFAULT_RCLONE_PATH: "/fake/rclone")


def _job(mode: str = "copy", excludes: str = "") -> dict:
    return {
        "id": 1,
        "name": "x",
        "local_path": "/local",
        "remote_name": "gdrive",
        "remote_path": "Backups/X",
        "mode": mode,
        "excludes": excludes,
    }


def test_build_command_copy(fake_rclone):
    cmd = rclone_backend._build_command(_job("copy"))
    assert cmd == ["/fake/rclone", "copy", "/local", "gdrive:Backups/X", "-v", "--stats=1s"]


def test_build_command_dry_run(fake_rclone):
    cmd = rclone_backend._build_command(_job("sync"), dry_run=True)
    assert "--dry-run" in cmd
    assert "--resync" not in cmd


def test_bisync_dry_run_does_not_force_resync(fake_rclone):
    cmd = rclone_backend._build_command(_job("bisync"), dry_run=True)
    assert "--dry-run" in cmd
    assert "--resync" not in cmd


def test_bisync_with_resync(fake_rclone):
    cmd = rclone_backend._build_command(_job("bisync"), resync=True)
    assert "--resync" in cmd
    assert "--dry-run" not in cmd
    assert "--resilient" not in cmd


def test_resync_ignored_outside_bisync(fake_rclone):
    cmd = rclone_backend._build_command(_job("copy"), resync=True)
    assert "--resync" not in cmd


def test_bisync_normal_run_includes_resilient_and_recover(fake_rclone):
    cmd = rclone_backend._build_command(_job("bisync"), resync=False)
    assert "--resilient" in cmd
    assert "--recover" in cmd
    assert "--resync" not in cmd


def test_copy_does_not_include_bisync_flags(fake_rclone):
    cmd = rclone_backend._build_command(_job("copy"))
    assert "--resilient" not in cmd
    assert "--recover" not in cmd


def test_sync_does_not_include_bisync_flags(fake_rclone):
    cmd = rclone_backend._build_command(_job("sync"))
    assert "--resilient" not in cmd
    assert "--recover" not in cmd


def test_excludes_appended(fake_rclone):
    cmd = rclone_backend._build_command(_job("copy", excludes="*.tmp\n  \nnode_modules/**"))
    assert cmd.count("--exclude") == 2
    assert "*.tmp" in cmd
    assert "node_modules/**" in cmd


def test_remote_path_strips_leading_slash(fake_rclone):
    job = _job("copy")
    job["remote_path"] = "/Backups/X"
    cmd = rclone_backend._build_command(job)
    assert "gdrive:Backups/X" in cmd


def test_summarize_keeps_relevant_lines():
    result = CommandResult(
        command=["rclone"],
        exit_code=0,
        stdout="2024/01/01 INFO Transferred: 5\nirrelevant chatter\n",
        stderr="",
        log_path="/tmp/x.log",
    )
    assert "Transferred" in rclone_backend.summarize(result)


def test_summarize_falls_back_to_tail():
    result = CommandResult(["rclone"], 1, "line1\nline2\nline3\n", "", "/tmp/x.log")
    assert "line3" in rclone_backend.summarize(result)


def test_summarize_handles_empty_failure():
    result = CommandResult(["rclone"], 1, "", "", "/tmp/x.log")
    assert "Failed" in rclone_backend.summarize(result)
    assert "OK" not in rclone_backend.summarize(replace(result, exit_code=1))


def test_summarize_filters_experimental_notice():
    result = CommandResult(
        ["rclone"], 1,
        "",
        "<5>NOTICE: bisync is EXPERIMENTAL. Don't use in production!\n<3>ERROR : Bisync aborted. Must run --resync to recover.\n",
        "/tmp/x.log",
    )
    summary = rclone_backend.summarize(result)
    assert "EXPERIMENTAL" not in summary
    assert "Must run --resync" in summary


def test_summarize_prioritizes_errors():
    result = CommandResult(
        ["rclone"], 1,
        "Transferred: 5\n",
        "ERROR : something broke\n",
        "/tmp/x.log",
    )
    summary = rclone_backend.summarize(result)
    assert summary.splitlines()[0].lower().startswith("error")


def _write_lock(dir_path, name, pid):
    import json
    lock = dir_path / name
    lock.write_text(json.dumps({"Session": name, "PID": str(pid)}), encoding="utf-8")
    return lock


def test_clear_stale_bisync_locks_removes_dead_pid(tmp_path, monkeypatch, fake_rclone):
    bisync = tmp_path / "bisync"
    bisync.mkdir()
    monkeypatch.setattr(rclone_backend, "_cache_dir", lambda path=rclone_backend.DEFAULT_RCLONE_PATH: tmp_path)
    monkeypatch.setattr(rclone_backend, "_pid_alive", lambda pid: False)
    lock = _write_lock(bisync, "stale..remote_.lck", 99999)

    removed = rclone_backend.clear_stale_bisync_locks()

    assert removed == ["stale..remote_.lck"]
    assert not lock.exists()


def test_clear_stale_bisync_locks_keeps_live_pid(tmp_path, monkeypatch, fake_rclone):
    bisync = tmp_path / "bisync"
    bisync.mkdir()
    monkeypatch.setattr(rclone_backend, "_cache_dir", lambda path=rclone_backend.DEFAULT_RCLONE_PATH: tmp_path)
    monkeypatch.setattr(rclone_backend, "_pid_alive", lambda pid: True)
    lock = _write_lock(bisync, "live..remote_.lck", 4321)

    removed = rclone_backend.clear_stale_bisync_locks()

    assert removed == []
    assert lock.exists()


def test_clear_stale_bisync_locks_skips_malformed(tmp_path, monkeypatch, fake_rclone):
    bisync = tmp_path / "bisync"
    bisync.mkdir()
    monkeypatch.setattr(rclone_backend, "_cache_dir", lambda path=rclone_backend.DEFAULT_RCLONE_PATH: tmp_path)
    monkeypatch.setattr(rclone_backend, "_pid_alive", lambda pid: False)
    bad = bisync / "bad..remote_.lck"
    bad.write_text("not json", encoding="utf-8")

    removed = rclone_backend.clear_stale_bisync_locks()

    assert removed == []
    assert bad.exists()


def test_clear_stale_bisync_locks_no_cache_dir(monkeypatch):
    monkeypatch.setattr(rclone_backend, "_cache_dir", lambda path=rclone_backend.DEFAULT_RCLONE_PATH: None)
    assert rclone_backend.clear_stale_bisync_locks() == []


def test_run_job_clears_locks_for_bisync(tmp_path, monkeypatch, fake_rclone):
    calls = []
    monkeypatch.setattr(rclone_backend, "clear_stale_bisync_locks", lambda path=rclone_backend.DEFAULT_RCLONE_PATH: calls.append(path) or [])
    monkeypatch.setattr(rclone_backend, "_run", lambda command, label, timeout=0: CommandResult(list(command), 0, "", "", "/tmp/x.log"))

    rclone_backend.run_job(_job("bisync"))
    assert len(calls) == 1


def test_run_job_skips_lock_clear_for_copy(monkeypatch, fake_rclone):
    calls = []
    monkeypatch.setattr(rclone_backend, "clear_stale_bisync_locks", lambda path=rclone_backend.DEFAULT_RCLONE_PATH: calls.append(path) or [])
    monkeypatch.setattr(rclone_backend, "_run", lambda command, label, timeout=0: CommandResult(list(command), 0, "", "", "/tmp/x.log"))

    rclone_backend.run_job(_job("copy"))
    assert calls == []
