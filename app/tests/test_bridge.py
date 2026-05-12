import pytest

from drive_sync_desktop import bridge as bridge_module
from drive_sync_desktop.bridge import Bridge


@pytest.fixture
def bridge(monkeypatch):
    monkeypatch.setattr(bridge_module, "list_remotes", lambda: ["drive"])
    return Bridge()


def _payload(name="test", **overrides):
    base = {
        "name": name,
        "local_path": "/tmp",
        "remote_name": "drive",
        "remote_path": "Backups/Test",
        "mode": "copy",
    }
    base.update(overrides)
    return base


def test_save_and_list_jobs(bridge):
    job_id = bridge.save_job(_payload())
    jobs = bridge.list_jobs()
    assert any(j["id"] == job_id and j["name"] == "test" for j in jobs)


def test_get_and_delete_job(bridge):
    job_id = bridge.save_job(_payload("alpha"))
    fetched = bridge.get_job(job_id)
    assert fetched["name"] == "alpha"
    bridge.delete_job(job_id)
    assert bridge.get_job(job_id) is None


def test_save_validates_required_fields(bridge):
    with pytest.raises(ValueError):
        bridge.save_job({"name": "no-paths"})


def test_save_validates_mode(bridge):
    with pytest.raises(ValueError):
        bridge.save_job(_payload(mode="weird"))


def test_save_normalizes_defaults(bridge):
    job_id = bridge.save_job(_payload("with-defaults"))
    job = bridge.get_job(job_id)
    assert job["mode"] == "copy"
    assert job["interval_minutes"] == 15
    assert job["dry_run_required"] == 1
    assert job["auto_sync"] == 0


def test_save_preserves_excludes_and_flags(bridge):
    job_id = bridge.save_job(_payload(
        "rich",
        mode="bisync",
        interval_minutes=5,
        auto_sync=True,
        excludes="*.tmp\nnode_modules/**",
    ))
    job = bridge.get_job(job_id)
    assert job["mode"] == "bisync"
    assert job["interval_minutes"] == 5
    assert job["auto_sync"] == 1
    assert job["dry_run_required"] == 1
    assert "*.tmp" in job["excludes"]


def test_save_always_forces_dry_run_required(bridge):
    job_id = bridge.save_job(_payload("force-dry", dry_run_required=False))
    assert bridge.get_job(job_id)["dry_run_required"] == 1


def test_save_autonames_from_local_path(bridge):
    job_id = bridge.save_job({
        "local_path": "/tmp/test/Documents",
        "remote_name": "drive",
        "remote_path": "Backups/Docs",
        "mode": "copy",
    })
    assert bridge.get_job(job_id)["name"] == "Documents"


def test_save_keeps_remote_path_empty_when_omitted(bridge):
    job_id = bridge.save_job({
        "local_path": "/tmp/test/Photos",
        "remote_name": "drive",
        "mode": "copy",
    })
    assert bridge.get_job(job_id)["remote_path"] == ""


def test_save_keeps_remote_path_explicit(bridge):
    job_id = bridge.save_job({
        "local_path": "/tmp/test/Photos",
        "remote_name": "drive",
        "remote_path": "PhotosBackup",
        "mode": "copy",
    })
    assert bridge.get_job(job_id)["remote_path"] == "PhotosBackup"


def test_connect_drive_generates_name_when_missing(monkeypatch, bridge):
    captured = {}
    monkeypatch.setattr(bridge_module, "add_drive_remote", lambda name, **kw: captured.setdefault("name", name))
    monkeypatch.setattr(bridge_module, "list_remotes", lambda: ["gdrive"])
    monkeypatch.setattr(bridge_module, "list_shared_drives", lambda name: [])
    result = bridge.connect_drive()
    assert result["name"] == "gdrive2"
    assert captured["name"] == "gdrive2"


def test_list_remotes_detailed_proxies_backend(monkeypatch, bridge):
    monkeypatch.setattr(bridge_module, "list_remotes_detailed", lambda: [{"name": "drive", "kind": "personal", "label": "Mi Drive"}])
    assert bridge.list_remotes_detailed() == [{"name": "drive", "kind": "personal", "label": "Mi Drive"}]


def test_list_remotes_detailed_swallows_errors(monkeypatch, bridge):
    def boom(): raise RuntimeError("rclone falló")
    monkeypatch.setattr(bridge_module, "list_remotes_detailed", boom)
    assert bridge.list_remotes_detailed() == []


def test_list_remote_folders_proxies(monkeypatch, bridge):
    monkeypatch.setattr(bridge_module, "list_remote_folders", lambda name, path: ["A", "B"])
    assert bridge.list_remote_folders("drive", "") == ["A", "B"]


def test_list_remote_folders_swallows_errors(monkeypatch, bridge):
    def boom(name, path): raise RuntimeError("rclone falló")
    monkeypatch.setattr(bridge_module, "list_remote_folders", boom)
    assert bridge.list_remote_folders("drive", "") == []


def test_make_remote_folder_proxies(monkeypatch, bridge):
    captured = {}
    monkeypatch.setattr(bridge_module, "make_remote_folder", lambda name, path: captured.update(name=name, path=path))
    bridge.make_remote_folder("drive", "Backups/New")
    assert captured == {"name": "drive", "path": "Backups/New"}


def test_list_remotes_uses_backend(bridge):
    assert bridge.list_remotes() == ["drive"]


def test_list_remotes_falls_back_to_empty(monkeypatch):
    def boom():
        raise RuntimeError("rclone no encontrado")
    monkeypatch.setattr(bridge_module, "list_remotes", boom)
    b = Bridge()
    assert b.list_remotes() == []


def test_pick_local_path_uses_injected_picker():
    b = Bridge(folder_picker=lambda: "/picked")
    assert b.pick_local_path() == "/picked"


def test_pick_local_path_returns_empty_when_no_picker():
    b = Bridge()
    assert b.pick_local_path() == ""


def test_runs_listing_after_dry_run(monkeypatch, bridge):
    job_id = bridge.save_job(_payload("for-runs"))
    monkeypatch.setattr(bridge_module, "run_one", lambda jid, dry_run, resync: (True, "ok"))
    result = bridge.run(job_id, dry_run=True, resync=False)
    assert result == {"ok": True, "summary": "ok"}


def test_run_blocks_bisync_without_baseline(monkeypatch, bridge):
    job_id = bridge.save_job(_payload("bi", mode="bisync"))
    monkeypatch.setattr(bridge_module, "run_one", lambda *a, **kw: pytest.fail("no debería ejecutarse"))
    result = bridge.run(job_id, dry_run=False, resync=False)
    assert result["ok"] is False
    assert result.get("needs_resync") is True


def test_run_allows_bisync_resync(monkeypatch, bridge):
    job_id = bridge.save_job(_payload("bi-resync", mode="bisync"))
    called = {}

    def fake_run(jid, dry_run, resync):
        called.update({"jid": jid, "resync": resync})
        return True, "baseline ok"

    monkeypatch.setattr(bridge_module, "run_one", fake_run)
    result = bridge.run(job_id, dry_run=False, resync=True)
    assert result == {"ok": True, "summary": "baseline ok"}
    assert called["resync"] is True


def test_list_jobs_marks_bisync_without_baseline(bridge):
    job_id = bridge.save_job(_payload("bi-mark", mode="bisync"))
    jobs = bridge.list_jobs()
    job = next(j for j in jobs if j["id"] == job_id)
    assert job["needs_baseline"] is True


def test_list_jobs_does_not_mark_copy(bridge):
    job_id = bridge.save_job(_payload("plain"))
    jobs = bridge.list_jobs()
    job = next(j for j in jobs if j["id"] == job_id)
    assert job["needs_baseline"] is False


def test_agent_status_proxies_service_control(monkeypatch, bridge):
    monkeypatch.setattr(bridge_module.service_control, "status", lambda: {"available": True, "active": False, "enabled": False})
    assert bridge.agent_status() == {"available": True, "active": False, "enabled": False}


def test_agent_enable_calls_and_returns_status(monkeypatch, bridge):
    called = {}
    monkeypatch.setattr(bridge_module.service_control, "enable", lambda: called.update(enable=True))
    monkeypatch.setattr(bridge_module.service_control, "status", lambda: {"available": True, "active": True, "enabled": True})
    result = bridge.agent_enable()
    assert called == {"enable": True}
    assert result["active"] is True


def test_save_blocks_duplicate_target(bridge):
    bridge.save_job(_payload("first"))
    with pytest.raises(ValueError, match="otra sync"):
        bridge.save_job(_payload("second"))


def test_save_allows_same_target_when_editing_same_job(bridge):
    job_id = bridge.save_job(_payload("editable"))
    same = _payload("editable")
    same["id"] = job_id
    same["interval_minutes"] = 99
    bridge.save_job(same)
    assert bridge.get_job(job_id)["interval_minutes"] == 99


def test_save_allows_different_target(bridge):
    bridge.save_job(_payload("a"))
    bridge.save_job(_payload("b", remote_path="Backups/Other"))


def test_agent_disable_calls_and_returns_status(monkeypatch, bridge):
    called = {}
    monkeypatch.setattr(bridge_module.service_control, "disable", lambda: called.update(disable=True))
    monkeypatch.setattr(bridge_module.service_control, "status", lambda: {"available": True, "active": False, "enabled": False})
    result = bridge.agent_disable()
    assert called == {"disable": True}
    assert result["active"] is False


def test_connect_drive_returns_shared_drives(monkeypatch, bridge):
    monkeypatch.setattr(bridge_module, "add_drive_remote", lambda name, **kw: "ok")
    monkeypatch.setattr(bridge_module, "list_shared_drives", lambda name: [{"id": "0AB", "name": "Equipo X"}])
    result = bridge.connect_drive("work")
    assert result["shared_drives"] == [{"id": "0AB", "name": "Equipo X"}]
    assert "ok" in result["output"]


def test_connect_drive_swallows_shared_drives_error(monkeypatch, bridge):
    monkeypatch.setattr(bridge_module, "add_drive_remote", lambda name, **kw: "ok")
    def boom(name): raise RuntimeError("rclone backend drives no soportado")
    monkeypatch.setattr(bridge_module, "list_shared_drives", boom)
    result = bridge.connect_drive("work")
    assert result["shared_drives"] == []


def test_select_shared_drive_proxies(monkeypatch, bridge):
    captured = {}
    monkeypatch.setattr(bridge_module, "set_shared_drive", lambda name, did: captured.update(name=name, did=did))
    bridge.select_shared_drive("work", "0AB")
    assert captured == {"name": "work", "did": "0AB"}
