# Drive Sync Desktop

[![tests](https://github.com/diegolis/drive-sync/actions/workflows/test.yml/badge.svg)](https://github.com/diegolis/drive-sync/actions/workflows/test.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)
[![python: 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](#)
[![platform: Linux](https://img.shields.io/badge/platform-Linux-lightgrey.svg)](#)

A Linux desktop app for syncing local folders with Google Drive, with a simple UX, using `rclone` as the sync engine.

## Status
Functional MVP. See [`app/`](./app) for the code and how to run it.

## Supported platforms
- **Linux with systemd** (tested on Ubuntu 24.04). The agent-as-a-service depends on `systemctl --user`.
- **macOS**: not supported. Google already provides [Google Drive for desktop](https://www.google.com/drive/download/) on macOS with a polished native experience; we recommend using that app.
- **Windows**: not supported for now.

## OAuth with Google Drive
The app **does not require** you to register your own OAuth client in Google Cloud. It uses `rclone`'s public shared client (the same flow `rclone config` uses by default). Authentication opens your browser and the token is stored locally in `~/.config/rclone/rclone.conf`. Nothing is sent to third parties beyond Google.

If you prefer to use your own `client_id`/`client_secret`, configure it manually via `rclone config` before running the app — existing remotes are respected.

## Goals
- configure one or more local folders
- point them to destinations in Google Drive
- run automatic synchronization
- see status, logs, errors, and conflicts
- minimize CLI usage

## Design principle
Don't reinvent the sync engine. The app orchestrates, validates, persists state, and shows UI; `rclone` does the heavy lifting.

## Stack
- Python 3.10+
- UI: embedded HTML/CSS/JS via [pywebview](https://pywebview.flowrl.com/) (WebKit on Linux)
- SQLite for local state
- `rclone` for syncing (the app triggers the Drive OAuth flow from the UI; you don't need to configure `rclone` by hand)
- systemd `--user` to run the agent as a service

## Layout
- [`app/`](./app): application, installer, and agent
- [`docs/mvp.md`](./docs/mvp.md): scope, features, and roadmap
- [`docs/architecture.md`](./docs/architecture.md): technical architecture
- [`config/example.sync.json`](./config/example.sync.json): example config (importable via `--import-config`)

## Important decision
Bidirectional sync (`bisync`) is supported, but the baseline must be initialized explicitly from the UI or with `--resync`. It is never enabled silently.

## Install

### Option 1 — `.deb` (Debian/Ubuntu)

Download the latest `drive-sync-desktop_<version>_all.deb` from the [releases page](https://github.com/diegolis/drive-sync/releases) and install:

```bash
sudo apt install ./drive-sync-desktop_*.deb
```

apt will pull `python3-webview`, `python3-pil`, GTK/WebKit bindings, and `rclone` from the official repos. If your apt rclone is older than 1.66, run the included helper once (no root needed):

```bash
drive-sync-desktop-update-rclone
```

### Option 2 — shell installer (any Linux with systemd)

```bash
cd app
chmod +x install.sh
./install.sh
drive-sync-desktop
```

`install.sh` will download a recent `rclone` to `~/.local/bin/rclone` if your system rclone is too old for `bisync --resilient`. It never touches the system rclone.

### Option 3 — `pip` (developers)

```bash
pip install --user .[tray]
```

## Contributing
See [CONTRIBUTING.md](./CONTRIBUTING.md). Bug reports and feature requests are tracked in [Issues](https://github.com/diegolis/drive-sync/issues).

## Security
See [SECURITY.md](./SECURITY.md) for the disclosure process.

## Code of Conduct
This project follows the [Contributor Covenant](./CODE_OF_CONDUCT.md).

## License
[MIT](./LICENSE).
