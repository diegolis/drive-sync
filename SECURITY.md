# Security policy

## Supported versions

Drive Sync Desktop is in active development. Only the latest commit on `main`
receives security fixes.

| Version | Supported |
|---------|-----------|
| latest  | ✅        |
| older   | ❌        |

## Reporting a vulnerability

**Do not open a public issue for security problems.** Public reports give
attackers a head start before users can patch.

Please report security issues privately:

- Open a [GitHub Security Advisory](https://github.com/diegolis/drive-sync/security/advisories/new) (preferred), or
- Email the maintainer (see the GitHub profile linked from the repo).

Include:

- A description of the issue and the affected component.
- Steps to reproduce, ideally with a minimal proof-of-concept.
- The impact you anticipate (data exposure, code execution, privilege
  escalation, etc.).
- Your name/handle if you want to be credited in the fix.

You can expect:

- An acknowledgement within **3 business days**.
- A clear next-step plan within **7 business days** (fix in progress, more
  information needed, or decision not to fix with reasoning).
- A coordinated public disclosure once a fix is available.

## Scope

In scope:

- The Python code in `app/drive_sync_desktop/`.
- The bundled frontend (`app/drive_sync_desktop/frontend/`).
- `install.sh` and `uninstall.sh`.

Out of scope (please report upstream):

- Bugs in `rclone` itself — report to [rclone/rclone](https://github.com/rclone/rclone/issues).
- Bugs in `pywebview`, `pystray`, `Pillow`, or other dependencies.
- Issues that require already-compromised local user privileges (an attacker
  who can write to `$HOME/.config/rclone/rclone.conf` already controls the
  Drive session by design).

## Threat model

- The app runs as your user account. It does not run as root or daemonize
  outside your user systemd scope.
- Network traffic is limited to whatever `rclone` does — Google Drive, plus
  the rclone OAuth flow.
- The local SQLite DB and per-run logs are created with mode `0600`; their
  parent directories with `0700`.
- `rclone.conf` permissions are managed by `rclone` itself (typically `0600`).

If you find a path that violates these assumptions, please report it.
