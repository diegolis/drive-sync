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
