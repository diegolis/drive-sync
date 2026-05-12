# MVP - Drive Sync Desktop

## What we're building
A desktop app for Linux that syncs local folders with Google Drive without forcing the user to use `rclone` manually.

## Real problem
Free options on Linux for automatic Drive sync are weak, discontinued, or hard to use. `rclone` works great, but its UX isn't designed for someone who wants to set up a folder and forget about it.

## MVP status

### Implemented
- [x] modern UI in HTML/CSS/JS embedded via pywebview (cards, modals, dark theme)
- [x] Google Drive onboarding with OAuth from the app (UI or `--add-remote`)
- [x] create/edit/delete jobs from the UI
- [x] `copy`, `sync`, and `bisync` modes
- [x] `--dry-run` with preview
- [x] preview of the `rclone` command before executing
- [x] explicit confirmation before destructive modes (`sync`, `bisync`)
- [x] baseline initialization for `bisync` ("Initialize bisync" button + `--resync` in CLI)
- [x] run history with stdout/stderr persisted
- [x] agent loop with interval-based scheduler
- [x] per-job lockfile to prevent concurrent runs
- [x] subprocess timeout (configurable via `RCLONE_TIMEOUT_SECONDS`)
- [x] timestamps in UTC
- [x] SQLite in WAL mode for UI + agent concurrency
- [x] configuration import from JSON (`--import-config`)
- [x] installer under `~/.local` with `.desktop` entry and systemd `--user` unit

### Out of scope for the MVP
- filesystem watcher (inotify) with debouncing
- sophisticated conflict detection
- full Drive explorer inside the app
- multiple cloud providers
- mobile integration

## Bidirectional sync: stance

`bisync` is supported but never enabled silently. The UI requires:
1. create the job in `bisync` mode
2. click "Initialize bisync" once to establish the baseline (`--resync`)
3. after that, each run goes without `--resync`

Accepted risks: a file edited on both sides, cross-deletions, concurrent renames. The resolution policy is defined by `rclone bisync`. Future improvements: a `conflicts` table and configurable resolution.

## UX

### Main screen
- topbar with brand, remote status, and a "+ New sync" button
- differentiated empty states: no remotes vs no jobs
- card grid: one card per sync with icon, path, mode (↑/⇒/⇄), colored status, and Sync / Dry run buttons

### "New sync" modal
- 3 visible fields: name, local folder (with native picker), Drive destination
- visual mode selector: 3 cards (Safe backup / Mirror / Bidirectional) with descriptions
- "Advanced options" collapsed: auto-sync, interval, excludes, dry-run required

### Detail modal
- header with name + shortened path
- actions: Dry run, Sync now, Initialize bisync (when applicable)
- recent runs with relative time and summary
- summarized configuration
- footer with Delete and Edit

### Connect Drive modal
- input for account name
- announces the browser will open and shows status while waiting

## Success criteria
- create a sync without touching a terminal ✅
- run `dry-run` and understand what will happen ✅
- run a real sync and audit the result ✅
- visible, actionable errors ✅
- no silent deletions (lock + confirmation + dry-run) ✅
