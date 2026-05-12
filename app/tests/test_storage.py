from datetime import datetime, timezone

from drive_sync_desktop import storage


def _sample_job(name: str = "docs") -> dict:
    return {
        "name": name,
        "local_path": "/tmp/x",
        "remote_name": "gdrive",
        "remote_path": "Backups/Docs",
        "mode": "copy",
        "interval_minutes": 10,
        "auto_sync": True,
        "dry_run_required": True,
        "excludes": "*.tmp\nnode_modules/**",
    }


def test_upsert_get_list_delete():
    storage.init_db()
    job_id = storage.upsert_job(_sample_job())
    fetched = storage.get_job(job_id)
    assert fetched["name"] == "docs"
    assert fetched["auto_sync"] == 1
    assert storage.list_jobs()[0]["id"] == job_id
    storage.delete_job(job_id)
    assert storage.get_job(job_id) is None


def test_find_job_by_name():
    storage.init_db()
    job_id = storage.upsert_job(_sample_job("alpha"))
    assert storage.find_job_by_name("alpha") == job_id
    assert storage.find_job_by_name("missing") is None


def test_run_lifecycle():
    storage.init_db()
    job_id = storage.upsert_job(_sample_job())
    run_id = storage.create_run(job_id, "sync", "rclone ...", "/tmp/log")
    storage.finish_run(run_id, "ok", 0, "transferido todo")
    runs = storage.list_runs(job_id)
    assert runs[0]["status"] == "ok"
    assert runs[0]["summary"] == "transferido todo"


def test_parse_sqlite_ts_returns_utc_aware():
    parsed = storage.parse_sqlite_ts("2026-01-15 12:34:56")
    assert parsed == datetime(2026, 1, 15, 12, 34, 56, tzinfo=timezone.utc)


def test_parse_sqlite_ts_handles_garbage():
    assert storage.parse_sqlite_ts(None) is None
    assert storage.parse_sqlite_ts("") is None
    assert storage.parse_sqlite_ts("not-a-date") is None


def test_has_baseline_run():
    storage.init_db()
    job_id = storage.upsert_job(_sample_job("bisync-job") | {"mode": "bisync"})
    assert storage.has_baseline_run(job_id) is False
    run_id = storage.create_run(job_id, "sync", "rclone bisync ...", "/tmp/log")
    storage.finish_run(run_id, "ok", 0, "ok")
    assert storage.has_baseline_run(job_id) is False
    resync_id = storage.create_run(job_id, "resync", "rclone bisync --resync", "/tmp/log2")
    storage.finish_run(resync_id, "ok", 0, "baseline")
    assert storage.has_baseline_run(job_id) is True


def test_has_baseline_run_ignores_failed_resync():
    storage.init_db()
    job_id = storage.upsert_job(_sample_job("bisync-failed") | {"mode": "bisync"})
    run_id = storage.create_run(job_id, "resync", "rclone bisync --resync", "/tmp/log")
    storage.finish_run(run_id, "error", 1, "boom")
    assert storage.has_baseline_run(job_id) is False


def test_has_baseline_run_false_when_recent_run_says_must_resync():
    storage.init_db()
    job_id = storage.upsert_job(_sample_job("bisync-broken") | {"mode": "bisync"})
    rid = storage.create_run(job_id, "resync", "rclone bisync --resync", "/tmp/log")
    storage.finish_run(rid, "ok", 0, "Bisync successful")
    assert storage.has_baseline_run(job_id) is True
    bad = storage.create_run(job_id, "sync", "rclone bisync", "/tmp/log2")
    storage.finish_run(bad, "error", 2, "Bisync aborted. Must run --resync to recover.")
    assert storage.has_baseline_run(job_id) is False


def test_has_baseline_run_ignores_old_errors_before_latest_resync():
    storage.init_db()
    job_id = storage.upsert_job(_sample_job("bi-recovered") | {"mode": "bisync"})
    bad_resync = storage.create_run(job_id, "resync", "rclone bisync --resync", "/tmp/log")
    storage.finish_run(bad_resync, "ok", 0, "Bisync successful (but listings empty)")
    bad_run = storage.create_run(job_id, "sync", "rclone bisync", "/tmp/log2")
    storage.finish_run(bad_run, "error", 2, "Bisync aborted. Must run --resync to recover.")
    assert storage.has_baseline_run(job_id) is False
    fresh = storage.create_run(job_id, "resync", "rclone bisync --resync", "/tmp/log3")
    storage.finish_run(fresh, "ok", 0, "Bisync successful")
    assert storage.has_baseline_run(job_id) is True


def test_latest_block_reason_empty_local():
    storage.init_db()
    job_id = storage.upsert_job(_sample_job("empty-loc") | {"mode": "bisync"})
    rid = storage.create_run(job_id, "sync", "rclone bisync", "/tmp/log")
    storage.finish_run(rid, "error", 7, "ERROR : Empty current Path1 listing. Cannot sync to an empty directory")
    assert storage.latest_block_reason(job_id) == "empty_local"


def test_latest_block_reason_needs_baseline():
    storage.init_db()
    job_id = storage.upsert_job(_sample_job("needs-base") | {"mode": "bisync"})
    rid = storage.create_run(job_id, "sync", "rclone bisync", "/tmp/log")
    storage.finish_run(rid, "error", 2, "Bisync aborted. Must run --resync to recover.")
    assert storage.latest_block_reason(job_id) == "needs_baseline"


def test_latest_block_reason_none_when_last_ok():
    storage.init_db()
    job_id = storage.upsert_job(_sample_job("clean") | {"mode": "bisync"})
    rid = storage.create_run(job_id, "sync", "rclone bisync", "/tmp/log")
    storage.finish_run(rid, "ok", 0, "Bisync successful")
    assert storage.latest_block_reason(job_id) is None


def test_latest_block_reason_none_for_unrelated_error():
    storage.init_db()
    job_id = storage.upsert_job(_sample_job("unrelated") | {"mode": "bisync"})
    rid = storage.create_run(job_id, "sync", "rclone bisync", "/tmp/log")
    storage.finish_run(rid, "error", 1, "network error connecting to drive")
    assert storage.latest_block_reason(job_id) is None


def test_has_baseline_run_true_for_unrelated_error():
    storage.init_db()
    job_id = storage.upsert_job(_sample_job("bisync-misc-err") | {"mode": "bisync"})
    rid = storage.create_run(job_id, "resync", "rclone bisync --resync", "/tmp/log")
    storage.finish_run(rid, "ok", 0, "Bisync successful")
    bad = storage.create_run(job_id, "sync", "rclone bisync", "/tmp/log2")
    storage.finish_run(bad, "error", 1, "network error connecting to drive")
    assert storage.has_baseline_run(job_id) is True
