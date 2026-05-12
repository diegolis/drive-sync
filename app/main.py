from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict

from drive_sync_desktop.agent import main as agent_main
from drive_sync_desktop.common import APP_NAME, AppInfo, db_path, ensure_dirs
from drive_sync_desktop.config_io import import_config
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
    parser.add_argument("--agent", action="store_true", help="Corre el agente en loop")
    parser.add_argument("--tray", action="store_true", help="Corre el icono de la bandeja")
    parser.add_argument("--self-test", action="store_true", help="Smoke test sin UI")
    parser.add_argument("--import-config", metavar="PATH", help="Importa jobs desde JSON")
    parser.add_argument("--add-remote", metavar="NAME", help="Conecta Google Drive vía OAuth y guarda el remote")
    return parser


def _run_add_remote(name: str) -> int:
    print(f"Conectando Google Drive como '{name}'. El browser se va a abrir para autorizar.")
    add_drive_remote(name, interactive=True)
    print(f"Remote '{name}' agregado.")
    return 0


def _no_display_message() -> str:
    return (
        f"{APP_NAME} necesita una sesión gráfica. No encontré DISPLAY/WAYLAND_DISPLAY.\n"
        "Abrilo desde tu escritorio o una terminal dentro de tu sesión gráfica.\n"
        "Si querés probarlo headless: xvfb-run -a ~/.local/bin/drive-sync-desktop"
    )


def main() -> int:
    parser = _build_parser()
    args, remaining = parser.parse_known_args()

    if args.self_test:
        return self_test()
    if args.add_remote:
        return _run_add_remote(args.add_remote)
    if args.import_config:
        count = import_config(args.import_config)
        print(f"Importados {count} jobs")
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
        print(f"No pude cargar la UI: {exc}\nInstalá Tkinter (ej: sudo apt install python3-tk).", file=sys.stderr)
        return 3
    ui_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
