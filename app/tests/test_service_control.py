import subprocess

import pytest

from drive_sync_desktop import service_control


def _result(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=stderr)


def test_status_unit_unknown(monkeypatch):
    monkeypatch.setattr(service_control.subprocess, "run", lambda *a, **kw: _result(1, ""))
    assert service_control.status() == {"available": False, "active": False, "enabled": False}


def test_status_systemctl_missing(monkeypatch):
    def boom(*a, **kw):
        raise FileNotFoundError("systemctl not found")
    monkeypatch.setattr(service_control.subprocess, "run", boom)
    assert service_control.status()["available"] is False


def test_status_active_and_enabled(monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if "list-unit-files" in cmd:
            return _result(0, stdout=service_control.UNIT_NAME + " enabled enabled\n")
        if "is-active" in cmd:
            return _result(0)
        if "is-enabled" in cmd:
            return _result(0)
        return _result(1)

    monkeypatch.setattr(service_control.subprocess, "run", fake_run)
    s = service_control.status()
    assert s == {"available": True, "active": True, "enabled": True}


def test_status_inactive(monkeypatch):
    def fake_run(cmd, **kw):
        if "list-unit-files" in cmd:
            return _result(0, stdout=service_control.UNIT_NAME + " disabled\n")
        if "is-active" in cmd:
            return _result(3)
        if "is-enabled" in cmd:
            return _result(1)
        return _result(1)

    monkeypatch.setattr(service_control.subprocess, "run", fake_run)
    assert service_control.status() == {"available": True, "active": False, "enabled": False}


def test_enable_runs_systemctl(monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return _result(0)

    monkeypatch.setattr(service_control.subprocess, "run", fake_run)
    service_control.enable()
    assert calls[0][:4] == ["systemctl", "--user", "enable", "--now"]
    assert calls[0][-1] == service_control.UNIT_NAME


def test_disable_runs_systemctl(monkeypatch):
    calls = []
    monkeypatch.setattr(service_control.subprocess, "run", lambda cmd, **kw: (calls.append(cmd), _result(0))[1])
    service_control.disable()
    assert calls[0][:4] == ["systemctl", "--user", "disable", "--now"]


def test_enable_raises_on_failure(monkeypatch):
    monkeypatch.setattr(service_control.subprocess, "run", lambda *a, **kw: _result(1, stderr="boom"))
    with pytest.raises(RuntimeError, match="boom"):
        service_control.enable()
