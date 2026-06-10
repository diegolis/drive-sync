from __future__ import annotations

import argparse
import fcntl
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from .common import ensure_dirs, runtime_dir
from .rclone_backend import CommandResult, preview_command, run_job, summarize
from .storage import (
    create_run,
    finish_run,
    get_job,
    has_baseline_run,
    init_db,
    latest_block_reason,
    list_jobs,
    mark_auto_resync,
    parse_sqlite_ts,
    touch_job_result,
)

AUTO_RESYNC_COOLDOWN = timedelta(minutes=10)


@contextmanager
def job_lock(job_id: int):
    ensure_dirs()
    lock_path = runtime_dir() / f"job-{job_id}.lock"
    with open(lock_path, "w", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("That job is already running")
        yield


def _due(job: dict) -> bool:
    if not job.get("auto_sync"):
        return False
    last = parse_sqlite_ts(job.get("last_run_at"))
    if last is None:
        return True
    delta = timedelta(minutes=int(job.get("interval_minutes") or 15))
    return datetime.now(timezone.utc) >= last + delta


def run_one(job_id: int, dry_run: bool = False, resync: bool = False) -> tuple[bool, str]:
    job = get_job(job_id)
    if not job:
        return False, "Job does not exist"
    return _execute(job, dry_run, resync)


def _execute(job: dict, dry_run: bool, resync: bool) -> tuple[bool, str]:
    run_type = "dry_run" if dry_run else ("resync" if resync else "sync")
    command = preview_command(job, dry_run=dry_run, resync=resync)
    with job_lock(int(job["id"])):
        result = run_job(job, dry_run=dry_run, resync=resync)
        return _persist(int(job["id"]), run_type, command, result)


def _persist(job_id: int, run_type: str, command: str, result: CommandResult) -> tuple[bool, str]:
    summary = summarize(result)
    run_id = create_run(job_id, run_type, command, result.log_path)
    status = "ok" if result.ok else "error"
    finish_run(run_id, status, result.exit_code, summary)
    touch_job_result(job_id, status, summary)
    return result.ok, summary


def loop(interval_seconds: int = 30) -> None:
    init_db()
    print("[drive-sync-agent] started")
    while True:
        _tick()
        time.sleep(interval_seconds)


def _tick() -> None:
    for job in list_jobs():
        if not _due(job):
            continue
        if _try_auto_recovery(job):
            continue
        skip_reason = _skip_reason(job)
        if skip_reason:
            print(f"[{job['name']}] skip: {skip_reason}")
            continue
        _safe_run(job)


def _needs_baseline(job: dict) -> bool:
    return not has_baseline_run(int(job["id"]))


def _skip_reason(job: dict) -> str | None:
    if _needs_baseline(job):
        return "bisync has no baseline"
    block = latest_block_reason(int(job["id"]))
    if block == "empty_local":
        return "one side is empty while the other has files (needs manual action)"
    if block == "needs_baseline":
        return "bisync needs to reinitialize the baseline"
    return None


def _try_auto_recovery(job: dict) -> bool:
    if not _wants_auto_recovery(job):
        return False
    if not _can_auto_recover(job):
        return False
    print(f"[{job['name']}] auto-recover: reinitializing baseline")
    mark_auto_resync(int(job["id"]))
    try:
        run_one(int(job["id"]), dry_run=False, resync=True)
    except Exception as exc:
        print(f"[{job['name']}] auto-recover error: {exc}")
    return True


def _wants_auto_recovery(job: dict) -> bool:
    if _needs_baseline(job):
        return True
    return latest_block_reason(int(job["id"])) in ("needs_baseline", "empty_local")


def _can_auto_recover(job: dict) -> bool:
    last_at = job.get("last_auto_resync_at")
    if not last_at:
        return True
    parsed = parse_sqlite_ts(last_at)
    if not parsed:
        return True
    return datetime.now(timezone.utc) >= parsed + AUTO_RESYNC_COOLDOWN


def _safe_run(job: dict) -> None:
    try:
        ok, summary = run_one(int(job["id"]), dry_run=False)
        print(f"[{job['name']}] {'OK' if ok else 'ERROR'}\n{summary}\n")
    except Exception as exc:
        print(f"[{job['name']}] ERROR: {exc}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", type=int, help="Run a single job by id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resync", action="store_true", help="Initialize bisync baseline")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval-seconds", type=int, default=30)
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    init_db()
    if args.once:
        ok, summary = run_one(args.once, dry_run=args.dry_run, resync=args.resync)
        print("OK" if ok else "ERROR")
        print(summary)
        return
    if args.loop:
        loop(args.interval_seconds)
        return
    parser.print_help()


if __name__ == "__main__":
    main()
