# Drive Sync Desktop MVP

Working app for Linux using Python + pywebview + SQLite + `rclone`.

## What it does
- desktop UI (HTML/CSS/JS via pywebview)
- create/edit/delete sync jobs
- bidirectional sync (`rclone bisync`) — the only mode, by design
- first run auto-initializes the baseline with a non-destructive merge (`--resync`)
- delete-protection on every run (`--max-delete`) and conflict resolution that never overwrites data
- `dry-run` and command preview before executing
- run history and per-run logs
- optional agent to run syncs on an interval (with lockfile)
- import jobs from JSON
- installer for `~/.local`

## Requirements
- Python 3.10+
- `rclone` installed on the system (the app handles the Drive OAuth flow)
- For the UI:
  - `pywebview` (`pip install --user pywebview`)
  - On Linux/Ubuntu: `sudo apt install python3-gi gir1.2-webkit2-4.1 libcairo2-dev`
- For the systemd agent unit: `systemctl --user`

## Run locally
```bash
cd app
PYTHONPATH=. python3 main.py
```

## Smoke test
```bash
PYTHONPATH=. python3 main.py --self-test
```

## Connect Google Drive
The first time you open the app, the UI offers to connect for you. If you prefer the CLI:
```bash
PYTHONPATH=. python3 main.py --add-remote gdrive
```
The browser opens, you authorize, and `rclone` stores the token in `~/.config/rclone/rclone.conf`.

## Import jobs from JSON
```bash
PYTHONPATH=. python3 main.py --import-config ../config/example.sync.json
```
Import is idempotent by name: re-importing a job with the same name updates it.

## Tests
```bash
python3 -m pytest
```

## Install
```bash
chmod +x install.sh uninstall.sh make-package.sh
./install.sh
```

## Use
```bash
drive-sync-desktop
```

## Agent

Manually:
```bash
drive-sync-desktop-agent --interval-seconds 30
```

As a systemd `--user` service:
```bash
systemctl --user enable --now drive-sync-desktop-agent.service
systemctl --user status drive-sync-desktop-agent.service
journalctl --user -u drive-sync-desktop-agent.service -f
```

### One-shot agent actions
```bash
drive-sync-desktop-agent --once 1                # run job 1
drive-sync-desktop-agent --once 1 --dry-run      # dry-run job 1
drive-sync-desktop-agent --once 1 --resync       # re-initialize the baseline (merges both sides)
```

## Environment configuration
- `RCLONE_PATH`: path to the `rclone` binary (default: search in `PATH`)
- `RCLONE_TIMEOUT_SECONDS`: timeout per run (default: `21600` = 6h)
- `DRIVE_SYNC_MAX_DELETE`: max percentage of files a run may delete before aborting (default: `50`)
- `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `XDG_RUNTIME_DIR`: XDG standard

## Package
```bash
./make-package.sh
```
