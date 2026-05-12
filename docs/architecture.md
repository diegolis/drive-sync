# Technical architecture

## Core decision
Use `rclone` as the sync backend and build on top of it: configuration, scheduler, persisted state, UI, and safety guardrails.

## Stack
- **Python 3.10+** for application logic
- **pywebview + HTML/CSS/JS** for the UI (WebKit on Linux). Frontend lives in `drive_sync_desktop/frontend/`.
- **SQLite** for local state (WAL mode)
- **systemd user units** for the agent-as-a-service
- **`rclone`** as a system dependency; the OAuth flow is triggered from the app

### Why this stack
- a single Python app, with a modern HTML/CSS UI, without rewriting any logic
- distribution as a `.tar.gz` and installation under `~/.local`
- the frontend is a static page: zero npm, no build step
- the real engine (`rclone`) handles the hard problems

## Components

### 1. UI layer (`drive_sync_desktop/ui.py` + `frontend/`)
Minimal pywebview host that opens a window loading `frontend/index.html`. All visual logic (cards, modals, states, toasts) lives in `frontend/app.js`, with a dark palette in `styles.css`. The UI calls methods on the Bridge exposed via `js_api`.

### 1b. Bridge (`drive_sync_desktop/bridge.py`)
Testable `Bridge` class with no dependency on webview. It exposes job CRUD, listing of remotes and runs, execution (`run`), Drive connection (`connect_drive`), and an injectable file picker. It is the only surface the JS code can call.

### 2. Sync orchestrator (`drive_sync_desktop/rclone_backend.py`)
Builds `rclone` commands from a job, runs them via `subprocess.run` with a timeout, captures stdout/stderr, logs to a file, and summarizes the output with a simple keyword-based heuristic.

### 3. Job scheduler (`drive_sync_desktop/agent.py`)
A loop that evaluates `_due(job)` with UTC timestamps and runs due jobs. Each job is serialized with a lockfile (`fcntl.flock` in `XDG_RUNTIME_DIR`).

### 4. State store (`drive_sync_desktop/storage.py`)
SQLite with two tables: `jobs` and `runs`. Uses `journal_mode=WAL` so the UI and the agent can run concurrently.

### 5. Config import (`drive_sync_desktop/config_io.py`)
Imports jobs from JSON (camelCase) into the DB. Idempotent by name.

### 6. Onboarding (`drive_sync_desktop/onboarding.py`)
Builds and runs `rclone config create <name> drive scope=drive config_is_local=true` to trigger Google OAuth. The UI offers this automatically when no remotes exist, and via a "Connect Drive…" button. CLI: `--add-remote NAME`.

## Sync model

### Modes
1. **`copy`**: uploads/updates, never deletes from the destination. Safe default.
2. **`sync`**: mirrors source to destination, can delete. Requires confirmation if `dry_run_required` is set.
3. **`bisync`**: bidirectional. Requires baseline initialization with `--resync` ("Initialize bisync" button in the UI, or `--resync` on the CLI).

### Base command
```
rclone <mode> <local_path> <remote>:<remote_path> -v --stats=1s [--dry-run] [--resync] [--exclude pattern]*
```

## Execution flow

### Dry run
1. user picks a job
2. UI validates the configuration
3. builds the command with `--dry-run`
4. runs it and captures output
5. shows the summary

### Real sync
1. lock the job via `fcntl.flock`
2. if mode is destructive (`sync`/`bisync`) and dry-run is required → explicit confirmation
3. run `rclone` with a timeout (default 6h, configurable via `RCLONE_TIMEOUT_SECONDS`)
4. persist `runs` in SQLite and update the `last_*` fields on `jobs`
5. release the lock by closing the file descriptor

## Operational safety

### Active guardrails
- explicit confirmation before `sync` or `bisync` when the job requires it
- per-job lockfile, preventing concurrent runs of the same job
- subprocess timeout to prevent the loop from hanging
- timestamps always in UTC (DB and comparisons)

### Conflicts
No conflict detection in the MVP. `bisync` delegates that logic to `rclone`. Roadmap: a `conflicts` table and a configurable resolution policy.

## Data schema

### `jobs`
- `id`, `name`, `local_path`, `remote_name`, `remote_path`
- `mode` (`copy` | `sync` | `bisync`)
- `interval_minutes`, `auto_sync`, `dry_run_required`
- `excludes` (one per line)
- `last_run_at`, `last_status`, `last_summary`
- `created_at`, `updated_at`

### `runs`
- `id`, `job_id`, `run_type` (`dry_run` | `sync` | `resync`)
- `status`, `started_at`, `finished_at`
- `exit_code`, `summary`, `command`, `log_path`

## File layout
```
$XDG_DATA_HOME/drive-sync-desktop/app.db        # SQLite state
$XDG_DATA_HOME/drive-sync-desktop/logs/         # per-run logs
$XDG_RUNTIME_DIR/drive-sync-desktop/job-*.lock  # lockfiles
```

## Technical risks and mitigations
| Risk | Mitigation |
|---|---|
| Fragile parsing of `rclone` output | Keyword-based heuristic + full log on disk for auditing |
| Hung subprocess | `subprocess.run(timeout=...)`, configurable |
| UI + agent concurrency over SQLite | `journal_mode=WAL` and `timeout=10s` on the connection |
| `bisync` with diverged baselines | Explicit "Initialize bisync" button for `--resync` |
| Drive API throttling | `rclone` already retries with backoff |

## Pending (post-MVP)
- filesystem watcher (notify/inotify) with debouncing
- conflict detection and UI surfacing
- `rclone --use-json-log` for structured summaries
