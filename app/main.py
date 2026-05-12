from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict

from drive_sync_desktop.agent import main as agent_main
from drive_sync_desktop.common import APP_NAME, AppInfo, db_path, ensure_dirs
from drive_sync_desktop.config_io import ConfigImportError, import_config
from drive_sync_desktop.onboarding import add_drive_remote
from drive_sync_desktop.rclone_backend import list_remotes, version
from drive_sync_desktop.storage import init_db, list_jobs


def self_test() -> int:
    ensure_dirs()
    init_db()
    info = {
        "app": asdict(AppInfo()),
        "db": str(db_path()),
        "jobs": len(list_jobs()),
        "rclone_version": version().splitlines()[0],
        "remotes": list_remotes(),
    }
    print(json.dumps(info, indent=2, ensure_ascii=False))
    return 0


def _has_graphical_session() -> bool:
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Drive Sync Desktop")
    parser.add_argument("--agent", action="store_true", help="Run the agent loop")
    parser.add_argument("--tray", action="store_true", help="Run the tray icon")
    parser.add_argument("--self-test", action="store_true", help="Smoke test without UI")
    parser.add_argument("--import-config", metavar="PATH", help="Import jobs from JSON")
    parser.add_argument("--add-remote", metavar="NAME", help="Connect Google Drive via OAuth and save the remote")
    return parser


def _run_add_remote(name: str) -> int:
    print(f"Connecting Google Drive as '{name}'. The browser will open to authorize.")
    add_drive_remote(name, interactive=True)
    print(f"Remote '{name}' added.")
    return 0


def _no_display_message() -> str:
    return (
        f"{APP_NAME} needs a graphical session. DISPLAY/WAYLAND_DISPLAY is not set.\n"
        "Launch it from your desktop or from a terminal inside your graphical session.\n"
        "For headless testing: xvfb-run -a ~/.local/bin/drive-sync-desktop"
    )


def main() -> int:
    parser = _build_parser()
    args, remaining = parser.parse_known_args()

    if args.self_test:
        return self_test()
    if args.add_remote:
        return _run_add_remote(args.add_remote)
    if args.import_config:
        try:
            count = import_config(args.import_config)
        except ConfigImportError as exc:
            print(f"Could not import config: {exc}", file=sys.stderr)
            return 4
        print(f"Imported {count} jobs")
        return 0
    if args.agent:
        sys.argv = [sys.argv[0], "--loop", *remaining]
        agent_main()
        return 0
    if args.tray:
        from drive_sync_desktop.tray import main as tray_main
        tray_main()
        return 0
    if not _has_graphical_session():
        print(_no_display_message(), file=sys.stderr)
        return 2
    return _run_ui()


def _run_ui() -> int:
    try:
        from drive_sync_desktop.ui import main as ui_main
    except ImportError as exc:
        print(
            f"Could not load the UI: {exc}\n"
            "Install pywebview and its system bindings.\n"
            "On Ubuntu/Debian:\n"
            "  sudo apt install python3-gi gir1.2-webkit2-4.1 libcairo2-dev\n"
            "  pip install --user pywebview",
            file=sys.stderr,
        )
        return 3
    ui_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
