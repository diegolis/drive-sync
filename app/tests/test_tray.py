import pytest

pytest.importorskip("pystray")
pytest.importorskip("PIL")

from drive_sync_desktop import tray


def test_classify_jobs_ok():
    jobs = [{"mode": "copy", "last_status": "ok"}, {"mode": "sync", "last_status": "ok"}]
    assert tray._classify_jobs(jobs) == "ok"


def test_classify_jobs_error_wins():
    jobs = [{"mode": "copy", "last_status": "ok"}, {"mode": "sync", "last_status": "error"}]
    assert tray._classify_jobs(jobs) == "error"


def test_classify_jobs_warn_when_bisync_pending():
    jobs = [{"mode": "bisync", "last_status": None}, {"mode": "copy", "last_status": "ok"}]
    assert tray._classify_jobs(jobs) == "warn"


def test_classify_jobs_no_jobs_returns_ok():
    assert tray._classify_jobs([]) == "ok"


def test_current_state_off_when_agent_inactive(monkeypatch):
    monkeypatch.setattr(tray.service_control, "status", lambda: {"available": True, "active": False})
    assert tray.current_state() == "off"


def test_current_state_uses_jobs_when_active(monkeypatch):
    monkeypatch.setattr(tray.service_control, "status", lambda: {"available": True, "active": True})
    monkeypatch.setattr(tray, "list_jobs", lambda: [{"mode": "copy", "last_status": "ok"}])
    assert tray.current_state() == "ok"


def test_current_state_error_when_any_job_failing(monkeypatch):
    monkeypatch.setattr(tray.service_control, "status", lambda: {"available": True, "active": True})
    monkeypatch.setattr(tray, "list_jobs", lambda: [{"mode": "bisync", "last_status": "error"}])
    assert tray.current_state() == "error"


def test_render_returns_image_for_each_state():
    for state in ("off", "ok", "warn", "error"):
        img = tray._render(state)
        assert img.size == (tray.ICON_SIZE, tray.ICON_SIZE)


def test_acquire_lock_blocks_second_instance(monkeypatch, tmp_path):
    monkeypatch.setattr(tray, "runtime_dir", lambda: tmp_path)
    monkeypatch.setattr(tray, "_LOCK_HANDLE", None, raising=False)
    assert tray._acquire_lock() is True
    assert tray._acquire_lock() is False
