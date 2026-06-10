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
- [x] bidirectional sync (`rclone bisync`) as the only mode
- [x] `--dry-run` with preview
- [x] preview of the `rclone` command before executing
- [x] automatic baseline on first run (non-destructive merge with `--resync`)
- [x] delete cap on every run (`--max-delete`, default 50%)
- [x] conflict resolution: newer file wins, older copy kept renamed
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

Every job is bidirectional (`rclone bisync`). The safety model replaces the old "never enable silently" rule, because the baseline initialization is non-destructive:

1. the **first run** (manual or from the agent) runs `--resync`, which merges both sides — files are only copied, never deleted
2. after that, each run propagates changes and deletions in both directions
3. every run carries `--max-delete` (default 50%): if one side suddenly lost most of its files (unmounted disk, emptied folder), the run aborts instead of wiping the other side
4. conflicts resolve to the newer file; the losing copy is kept renamed

Accepted risks: concurrent renames, conflict-renamed copies needing manual cleanup. Future improvements: a `conflicts` table and UI surfacing.

## UX

### Main screen
- topbar with brand, remote status, and a "+ New sync" button
- differentiated empty states: no remotes vs no jobs
- card grid: one card per sync with icon, path, ⇄ route, colored status, and Sync / Dry run buttons

### "New sync" modal
- 3 main fields: local folder (with native picker), account, Drive destination
- always-visible options: auto-sync (on by default, every 15 min), name, excludes

### Detail modal
- header with name + shortened path
- actions: Dry run, Sync now, Re-initialize (merge)
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
- no silent mass deletions (lock + non-destructive first merge + `--max-delete`) ✅
