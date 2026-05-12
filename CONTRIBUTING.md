# Contributing to Drive Sync Desktop

Thanks for your interest! This project is small and opinionated — before sending a large PR, please open an issue to discuss the approach.

## Requirements
- Linux with systemd (Ubuntu 24.04 tested)
- Python 3.10+
- `rclone` 1.66+ (for `bisync --resilient`). The `install.sh` script downloads a suitable version automatically to `~/.local/bin` if it can't find one.

## Development setup
```bash
git clone <repo>
cd drive-sync/app
pip install --user -r requirements.txt
PYTHONPATH=. python3 main.py        # run the app
PYTHONPATH=. python3 main.py --self-test
```

## Tests
```bash
cd app
python3 -m pytest
```
Tests do not touch real rclone or the filesystem outside of `tmp_path`/monkeypatch. If you add anything that uses `subprocess`, mock it.

## Packaging

Tarball (vendor-neutral):
```bash
cd app
./make-package.sh   # produces dist/drive-sync-desktop-<version>.tar.gz
```

Debian package:
```bash
scripts/build-deb.sh   # produces dist/drive-sync-desktop_<version>_all.deb
```
The `.deb` depends on `python3-webview` and other apt-packaged runtime deps. Inspect what you built with `dpkg-deb -c` and `dpkg-deb -I`.

## PR style
- Small, focused changes.
- If you touch `rclone_backend.py`, add/update tests in `tests/test_rclone_backend.py`.
- If you touch the SQLite schema, write an explicit migration in `storage.py` and test it.
- Don't add new dependencies without justifying them in the PR.

## Reporting bugs
Include:
- Distro + Python version + `rclone` version (`rclone version`).
- Job log (under `~/.local/share/drive-sync-desktop/logs/`).
- Steps to reproduce.

## License
By contributing you agree that your code will be released under the project's [MIT license](./LICENSE).
