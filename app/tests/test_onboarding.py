import subprocess

import pytest

from drive_sync_desktop import onboarding, rclone_backend
from drive_sync_desktop.rclone_backend import RcloneError


@pytest.fixture
def fake_rclone(monkeypatch):
    monkeypatch.setattr(onboarding, "detect_rclone", lambda path=rclone_backend.DEFAULT_RCLONE_PATH: "/fake/rclone")
    monkeypatch.setattr(onboarding, "list_remotes", lambda path=rclone_backend.DEFAULT_RCLONE_PATH: [])
    monkeypatch.setattr(onboarding, "_backup_config", lambda path: None)


def _fake_run_ok(command, **kwargs):
    return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")


def _fake_run_fail(command, **kwargs):
    return subprocess.CompletedProcess(command, 1, stdout="", stderr="oauth aborted")


def test_build_command_default_scope(fake_rclone):
    cmd = onboarding.build_add_remote_command("gdrive")
    assert cmd == [
        "/fake/rclone",
        "config",
        "create",
        "gdrive",
        "drive",
        "scope=drive",
        "config_is_local=true",
    ]


def test_build_command_custom_scope(fake_rclone):
    cmd = onboarding.build_add_remote_command("work", scope="drive.readonly")
    assert "scope=drive.readonly" in cmd


def test_rejects_invalid_name(fake_rclone):
    with pytest.raises(ValueError):
        onboarding.add_drive_remote("")
    with pytest.raises(ValueError):
        onboarding.add_drive_remote("with spaces")
    with pytest.raises(ValueError):
        onboarding.add_drive_remote("drive;rm -rf /")


def test_accepts_valid_names(fake_rclone, monkeypatch):
    monkeypatch.setattr(onboarding.subprocess, "run", _fake_run_ok)
    onboarding.add_drive_remote("gdrive")
    onboarding.add_drive_remote("work-laptop_2")


def test_non_interactive_returns_output(fake_rclone, monkeypatch):
    monkeypatch.setattr(onboarding.subprocess, "run", _fake_run_ok)
    output = onboarding.add_drive_remote("gdrive", interactive=False)
    assert "ok" in output


def test_non_interactive_raises_on_failure(fake_rclone, monkeypatch):
    monkeypatch.setattr(onboarding.subprocess, "run", _fake_run_fail)
    with pytest.raises(RcloneError):
        onboarding.add_drive_remote("gdrive", interactive=False)


def test_rejects_existing_remote(monkeypatch):
    monkeypatch.setattr(onboarding, "detect_rclone", lambda path=rclone_backend.DEFAULT_RCLONE_PATH: "/fake/rclone")
    monkeypatch.setattr(onboarding, "list_remotes", lambda path=rclone_backend.DEFAULT_RCLONE_PATH: ["drive", "work"])
    monkeypatch.setattr(onboarding, "_backup_config", lambda path: None)
    monkeypatch.setattr(onboarding.subprocess, "run", _fake_run_ok)
    with pytest.raises(RcloneError) as exc:
        onboarding.add_drive_remote("drive")
    assert "already exists" in str(exc.value)


def test_list_shared_drives_parses_json(monkeypatch):
    monkeypatch.setattr(onboarding, "detect_rclone", lambda path=rclone_backend.DEFAULT_RCLONE_PATH: "/fake/rclone")

    def fake_run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, stdout='[{"id":"0AB","name":"Equipo X"},{"id":"0CD","name":"Marketing"}]', stderr="")

    monkeypatch.setattr(onboarding.subprocess, "run", fake_run)
    drives = onboarding.list_shared_drives("gdrive")
    assert drives == [{"id": "0AB", "name": "Equipo X"}, {"id": "0CD", "name": "Marketing"}]


def test_list_shared_drives_handles_empty(monkeypatch):
    monkeypatch.setattr(onboarding, "detect_rclone", lambda path=rclone_backend.DEFAULT_RCLONE_PATH: "/fake/rclone")
    monkeypatch.setattr(onboarding.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, stdout="", stderr=""))
    assert onboarding.list_shared_drives("gdrive") == []


def test_list_shared_drives_raises_on_error(monkeypatch):
    monkeypatch.setattr(onboarding, "detect_rclone", lambda path=rclone_backend.DEFAULT_RCLONE_PATH: "/fake/rclone")
    monkeypatch.setattr(onboarding.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, stdout="", stderr="bad"))
    with pytest.raises(onboarding.RcloneError):
        onboarding.list_shared_drives("gdrive")


def test_set_shared_drive_runs_config_update(monkeypatch):
    monkeypatch.setattr(onboarding, "detect_rclone", lambda path=rclone_backend.DEFAULT_RCLONE_PATH: "/fake/rclone")
    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(onboarding.subprocess, "run", fake_run)
    onboarding.set_shared_drive("gdrive", "0AB123")
    assert captured["cmd"] == ["/fake/rclone", "config", "update", "gdrive", "team_drive=0AB123"]


def test_set_shared_drive_rejects_bad_id(monkeypatch):
    monkeypatch.setattr(onboarding, "detect_rclone", lambda path=rclone_backend.DEFAULT_RCLONE_PATH: "/fake/rclone")
    with pytest.raises(ValueError):
        onboarding.set_shared_drive("gdrive", "; rm -rf /")


def test_backup_path_is_returned(monkeypatch, tmp_path):
    fake_conf = tmp_path / "rclone.conf"
    fake_conf.write_text("[old]\ntype=drive\n", encoding="utf-8")

    def fake_config_path(path):
        return fake_conf

    monkeypatch.setattr(onboarding, "detect_rclone", lambda path=rclone_backend.DEFAULT_RCLONE_PATH: "/fake/rclone")
    monkeypatch.setattr(onboarding, "list_remotes", lambda path=rclone_backend.DEFAULT_RCLONE_PATH: [])
    monkeypatch.setattr(onboarding, "_rclone_config_path", fake_config_path)
    monkeypatch.setattr(onboarding.subprocess, "run", _fake_run_ok)

    output = onboarding.add_drive_remote("nuevo", interactive=False)
    backup = fake_conf.with_suffix(fake_conf.suffix + ".bak")
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == "[old]\ntype=drive\n"
    assert str(backup) in output
