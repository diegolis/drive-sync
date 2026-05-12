from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterable

from .common import db_path, ensure_dirs

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  local_path TEXT NOT NULL,
  remote_name TEXT NOT NULL,
  remote_path TEXT NOT NULL,
  mode TEXT NOT NULL DEFAULT 'copy',
  interval_minutes INTEGER NOT NULL DEFAULT 15,
  auto_sync INTEGER NOT NULL DEFAULT 0,
  excludes TEXT NOT NULL DEFAULT '',
  dry_run_required INTEGER NOT NULL DEFAULT 1,
  last_run_at TEXT,
  last_status TEXT,
  last_summary TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id INTEGER NOT NULL,
  run_type TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at TEXT,
  exit_code INTEGER,
  summary TEXT,
  log_path TEXT,
  command TEXT,
  FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
);
"""


def connect() -> sqlite3.Connection:
    ensure_dirs()
    path = db_path()
    conn = sqlite3.connect(path, timeout=10.0)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    if "last_auto_resync_at" not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN last_auto_resync_at TEXT")


def parse_sqlite_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


@contextmanager
def db() -> Iterable[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def list_jobs() -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute("SELECT * FROM jobs ORDER BY updated_at DESC, id DESC").fetchall()
    return [dict(r) for r in rows]


def get_job(job_id: int) -> dict[str, Any] | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def find_job_by_name(name: str) -> int | None:
    with db() as conn:
        row = conn.execute("SELECT id FROM jobs WHERE name = ?", (name,)).fetchone()
    return int(row["id"]) if row else None


def find_duplicate_target(local_path: str, remote_name: str, remote_path: str, exclude_id: int | None = None) -> int | None:
    sql = "SELECT id FROM jobs WHERE local_path=? AND remote_name=? AND remote_path=?"
    params: list[Any] = [local_path, remote_name, remote_path]
    if exclude_id is not None:
        sql += " AND id != ?"
        params.append(int(exclude_id))
    with db() as conn:
        row = conn.execute(sql, tuple(params)).fetchone()
    return int(row["id"]) if row else None


def upsert_job(job: dict[str, Any]) -> int:
    fields = (
        job["name"],
        job["local_path"],
        job["remote_name"],
        job["remote_path"],
        job["mode"],
        int(job.get("interval_minutes", 15) or 15),
        1 if job.get("auto_sync") else 0,
        job.get("excludes", ""),
        1 if job.get("dry_run_required", True) else 0,
    )
    with db() as conn:
        if job.get("id"):
            conn.execute(
                """
                UPDATE jobs
                SET name=?, local_path=?, remote_name=?, remote_path=?, mode=?,
                    interval_minutes=?, auto_sync=?, excludes=?, dry_run_required=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (*fields, job["id"]),
            )
            return int(job["id"])
        cur = conn.execute(
            """
            INSERT INTO jobs (name, local_path, remote_name, remote_path, mode, interval_minutes, auto_sync, excludes, dry_run_required)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            fields,
        )
        return int(cur.lastrowid)


def delete_job(job_id: int) -> None:
    with db() as conn:
        conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))


def create_run(job_id: int, run_type: str, command: str, log_path: str) -> int:
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO runs (job_id, run_type, status, command, log_path) VALUES (?, ?, 'running', ?, ?)",
            (job_id, run_type, command, log_path),
        )
        return int(cur.lastrowid)


def finish_run(run_id: int, status: str, exit_code: int, summary: str) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE runs SET status=?, exit_code=?, summary=?, finished_at=CURRENT_TIMESTAMP WHERE id=?",
            (status, exit_code, summary, run_id),
        )


def touch_job_result(job_id: int, status: str, summary: str) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE jobs SET last_run_at=CURRENT_TIMESTAMP, last_status=?, last_summary=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (status, summary, job_id),
        )


def has_baseline_run(job_id: int) -> bool:
    with db() as conn:
        latest_resync = conn.execute(
            "SELECT id FROM runs WHERE job_id = ? AND run_type = 'resync' AND status = 'ok' ORDER BY id DESC LIMIT 1",
            (job_id,),
        ).fetchone()
        if not latest_resync:
            return False
        broken = conn.execute(
            "SELECT summary FROM runs WHERE job_id = ? AND status = 'error' AND id > ? ORDER BY id DESC LIMIT 1",
            (job_id, latest_resync["id"]),
        ).fetchone()
    if broken and _baseline_broken(broken["summary"]):
        return False
    return True


def _baseline_broken(summary: str | None) -> bool:
    if not summary:
        return False
    low = summary.lower()
    return any(p in low for p in ("must run --resync", "cannot find prior", "empty prior"))


def latest_block_reason(job_id: int) -> str | None:
    with db() as conn:
        row = conn.execute(
            "SELECT status, summary FROM runs WHERE job_id = ? ORDER BY id DESC LIMIT 1",
            (job_id,),
        ).fetchone()
    if not row or row["status"] != "error":
        return None
    return _classify_block(row["summary"])


def _classify_block(summary: str | None) -> str | None:
    if not summary:
        return None
    low = summary.lower()
    if "empty current path" in low:
        return "empty_local"
    if _baseline_broken(low):
        return "needs_baseline"
    return None


def latest_run(job_id: int) -> dict[str, Any] | None:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM runs WHERE job_id = ? ORDER BY id DESC LIMIT 1",
            (job_id,),
        ).fetchone()
    return dict(row) if row else None


def mark_auto_resync(job_id: int) -> None:
    with db() as conn:
        conn.execute("UPDATE jobs SET last_auto_resync_at = CURRENT_TIMESTAMP WHERE id = ?", (job_id,))


def list_runs(job_id: int, limit: int = 20) -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM runs WHERE job_id = ? ORDER BY id DESC LIMIT ?",
            (job_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]
