"""Console-script entry points used by `pip install`.

The hand-rolled `install.sh` writes its own shell wrappers; this module exists
for users who install via `pip install drive-sync-desktop` and rely on the
console-script entry points declared in pyproject.toml.
"""
from __future__ import annotations

import sys


def run_ui() -> int:
    import argparse

    from .agent import main as agent_main
    from .common import APP_NAME
    from .ui import main as ui_main

    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--agent", action="store_true")
    parser.add_argument("--tray", action="store_true")
    args, remaining = parser.parse_known_args()

    if args.agent:
        sys.argv = [sys.argv[0], "--loop", *remaining]
        agent_main()
        return 0
    if args.tray:
        from .tray import main as tray_main
        tray_main()
        return 0
    ui_main()
    return 0


def run_agent() -> int:
    from .agent import main as agent_main

    sys.argv = [sys.argv[0], "--loop", *sys.argv[1:]]
    agent_main()
    return 0


def run_tray() -> int:
    from .tray import main as tray_main

    tray_main()
    return 0
