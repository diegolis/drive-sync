from datetime import datetime, timedelta, timezone

import pytest

from drive_sync_desktop import agent


def _now_utc_str(offset_minutes: int = 0) -> str:
    moment = datetime.now(timezone.utc) - timedelta(minutes=offset_minutes)
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def test_due_skipped_when_auto_sync_off():
    job = {"auto_sync": False, "interval_minutes": 5, "last_run_at": None}
    assert agent._due(job) is False


def test_due_true_when_never_ran():
    job = {"auto_sync": True, "interval_minutes": 5, "last_run_at": None}
    assert agent._due(job) is True


def test_due_false_when_recent():
    job = {"auto_sync": True, "interval_minutes": 30, "last_run_at": _now_utc_str(1)}
    assert agent._due(job) is False


def test_due_true_when_interval_elapsed():
    job = {"auto_sync": True, "interval_minutes": 5, "last_run_at": _now_utc_str(10)}
    assert agent._due(job) is True


def test_due_handles_invalid_timestamp():
    job = {"auto_sync": True, "interval_minutes": 5, "last_run_at": "garbage"}
    assert agent._due(job) is True


def test_job_lock_blocks_concurrent_acquire():
    with agent.job_lock(99):
        try:
            with agent.job_lock(99):
                raised = False
        except RuntimeError as exc:
            raised = "already running" in str(exc)
        assert raised


def test_needs_baseline_only_for_bisync_without_resync(monkeypatch):
    monkeypatch.setattr(agent, "has_baseline_run", lambda jid: False)
    assert agent._needs_baseline({"id": 1, "mode": "bisync"}) is True
    assert agent._needs_baseline({"id": 2, "mode": "copy"}) is False
    assert agent._needs_baseline({"id": 3, "mode": "sync"}) is False


def test_needs_baseline_false_when_baseline_exists(monkeypatch):
    monkeypatch.setattr(agent, "has_baseline_run", lambda jid: True)
    assert agent._needs_baseline({"id": 1, "mode": "bisync"}) is False


def test_tick_auto_recovers_bisync_without_baseline(monkeypatch, capsys):
    monkeypatch.setattr(agent, "list_jobs", lambda: [{"id": 1, "name": "bi", "mode": "bisync", "auto_sync": True, "interval_minutes": 1, "last_run_at": None, "last_auto_resync_at": None}])
    monkeypatch.setattr(agent, "has_baseline_run", lambda jid: False)
    monkeypatch.setattr(agent, "latest_block_reason", lambda jid: None)
    monkeypatch.setattr(agent, "mark_auto_resync", lambda jid: None)
    monkeypatch.setattr(agent, "_safe_run", lambda job: pytest.fail("no debería correr sync sin resync primero"))
    resync_calls = []
    monkeypatch.setattr(agent, "run_one", lambda jid, dry_run=False, resync=False: (resync_calls.append({"jid": jid, "resync": resync}), (True, "ok"))[1])
    agent._tick()
    assert resync_calls == [{"jid": 1, "resync": True}]
    assert "auto-recover" in capsys.readouterr().out.lower()


def test_tick_skips_when_auto_recover_in_cooldown(monkeypatch, capsys):
    recent = (datetime.now(timezone.utc) - timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M:%S")
    monkeypatch.setattr(agent, "list_jobs", lambda: [{"id": 1, "name": "bi", "mode": "bisync", "auto_sync": True, "interval_minutes": 1, "last_run_at": None, "last_auto_resync_at": recent}])
    monkeypatch.setattr(agent, "has_baseline_run", lambda jid: False)
    monkeypatch.setattr(agent, "latest_block_reason", lambda jid: None)
    monkeypatch.setattr(agent, "_safe_run", lambda job: pytest.fail("no debería correr"))
    monkeypatch.setattr(agent, "run_one", lambda *a, **kw: pytest.fail("no debería resync"))
    agent._tick()
    assert "skip" in capsys.readouterr().out.lower()


def test_tick_runs_bisync_with_baseline(monkeypatch):
    monkeypatch.setattr(agent, "list_jobs", lambda: [{"id": 1, "name": "bi", "mode": "bisync", "auto_sync": True, "interval_minutes": 1, "last_run_at": None, "last_auto_resync_at": None}])
    monkeypatch.setattr(agent, "has_baseline_run", lambda jid: True)
    monkeypatch.setattr(agent, "latest_block_reason", lambda jid: None)
    called = {}
    monkeypatch.setattr(agent, "_safe_run", lambda job: called.update(job=job))
    agent._tick()
    assert called["job"]["id"] == 1


def test_tick_auto_recovers_when_side_empty(monkeypatch):
    monkeypatch.setattr(agent, "list_jobs", lambda: [{"id": 1, "name": "ctx", "mode": "bisync", "auto_sync": True, "interval_minutes": 1, "last_run_at": None, "last_auto_resync_at": None}])
    monkeypatch.setattr(agent, "has_baseline_run", lambda jid: True)
    monkeypatch.setattr(agent, "latest_block_reason", lambda jid: "empty_local")
    monkeypatch.setattr(agent, "mark_auto_resync", lambda jid: None)
    monkeypatch.setattr(agent, "_safe_run", lambda job: pytest.fail("no debería correr sync"))
    resync_calls = []
    monkeypatch.setattr(agent, "run_one", lambda jid, dry_run=False, resync=False: (resync_calls.append({"jid": jid, "resync": resync}), (True, "ok"))[1])
    agent._tick()
    assert resync_calls == [{"jid": 1, "resync": True}]


def test_tick_skips_when_side_empty_in_cooldown(monkeypatch, capsys):
    recent = (datetime.now(timezone.utc) - timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M:%S")
    monkeypatch.setattr(agent, "list_jobs", lambda: [{"id": 1, "name": "ctx", "mode": "bisync", "auto_sync": True, "interval_minutes": 1, "last_run_at": None, "last_auto_resync_at": recent}])
    monkeypatch.setattr(agent, "has_baseline_run", lambda jid: True)
    monkeypatch.setattr(agent, "latest_block_reason", lambda jid: "empty_local")
    monkeypatch.setattr(agent, "_safe_run", lambda job: pytest.fail("no debería correr"))
    monkeypatch.setattr(agent, "run_one", lambda *a, **kw: pytest.fail("no debería resync"))
    agent._tick()
    assert "skip" in capsys.readouterr().out.lower()
